# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2005 Jörg Lehmann <joerg@luga.de>
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

import sys, threading, traceback
import events, hub, log

class service(threading.Thread):

    def __init__(self, name, daemonize=False, hub=hub._defaulthub):
        threading.Thread.__init__(self)
        # as independent thread, we want our own event and request channel
        # and need at least respond to a quit event
        self.name = name
        self.setName("%s service" % name)
        self.channel = hub.newchannel()
        self.channel.subscribe(events.quit, self.quit)
        self.done = False
        self.setDaemon(daemonize)
        log.debug("started %s service" % self.name)

    def resetafterexception(self):
        """ called after an exception has occured during the event/request handling

        If not reset is possible, an exception can be raised which will lead
        to the termination of the service.
        """
        pass

    def work(self):
        """ do the job """
        self.channel.process(block=True)

    def run(self):
        # main loop of the service
        while not self.done:
            # process events and catch all unhandled exceptions
            try:
                self.work()
            except Exception, e:
                log.debug_traceback()
                self.resetafterexception()

    # event handlers

    def quit(self, event):
        self.done = True
