# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002 Jörg Lehmann <joerg@luga.de>
#
# This file is part of PyTone (http://www.luga.de/pytone/)
#
# PyTone is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2
# as published by the Free Software Foundation.
#
# PyTone is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PyTone; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import time
import events, hub
import service

class timer(service.service):

    """ service which sends events at specified times """

    def __init__(self):
        """ constructs timer, which sends its events through eventhub """
        service.service.__init__(self, "timer")
        
        # each element in alarms is a tuple (alarmtime, event, repeat)
        self.alarms = []

        self.channel.subscribe(events.sendeventat, self.sendeventat)        
        self.channel.subscribe(events.sendeventin, self.sendeventin)

    def work(self):
        # TODO we could look for the next event and set the
        # timeout accordingly
        self.channel.process(block=True, timeout=0.5)
        acttime = time.time()
        for alarmtime, event, repeat in self.alarms:
            if alarmtime <= acttime:
                hub.notify(event)
                self.alarms.remove((alarmtime, event, repeat))
                if repeat:
                    self.alarms.append((alarmtime+repeat, event, repeat))

    def _sendeventat(self, event, alarmtime, repeat, replace):
        if replace:
            for i in range(len(self.alarms)):
                aalarmtime, aevent, arepeat = self.alarms[i]
                if aevent is event and arepeat==repeat:
                    self.alarms[i] = (alarmtime, event, repeat)
                    return

        self.alarms.append((alarmtime, event, repeat))

    # event handlers

    def sendeventat(self, event, alarmtime, repeat=False, replace=False):
        self._sendeventat(event.event, event.alarmtime, event.repeat, event.replace)
        
    def sendeventin(self, event):
        acttime = time.time()
        self._sendeventat(event.event, acttime+event.alarmtimediff, event.repeat, event.replace)
