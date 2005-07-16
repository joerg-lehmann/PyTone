# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2003, 2004 Jörg Lehmann <joerg@luga.de>
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

import copy, service
import hub, events, requests
import network

class player(service.service):
    def __init__(self, id, playlistid, networklocation):
        service.service.__init__(self, "remote player")
        self.id = id
        self.playlistid = playlistid
        self.networklocation = networklocation
        self.remoteplayerid = "main"

        self.networkchannel = network.clientchannel(self.networklocation)
        #self.networkchannel.transmit(events.updatesong)
        #self.networkchannel.transmit(events.updatealbum)
        #self.networkchannel.transmit(events.updateartist)
        #self.networkchannel.transmit(events.playlistaddsong)
        self.networkchannel.subscribe(events.playbackinfochanged, self.playbackinfochanged)

        # for playlists
        self.networkchannel.subscribe(events.playlistchanged, self.playlistchanged)
        self.networkchannel.start()

        # provide player service
        self.channel.subscribe(events.playerevent, self.playerevent)
        
        # we also provide a playlist service
        self.channel.subscribe(events.playlistevent, self.playlistevent)
        self.channel.supply(requests.playlistgetcontents, self.playlistgetcontents)
        
    # event handler

    def playbackinfochanged(self, event):
        # this is called by the networkchannel, so it should be (and is) thread safe
        event.playerid = self.id
        hub.notify(event)

    def playerevent(self, event):
        # we have to copy the event, because another thread may also access it
        event = copy.copy(event)
        event.playerid = self.remoteplayerid
        self.networkchannel.notify(event)

    def playlistevent(self, event):
        self.networkchannel.notify(event)

    def playlistchanged(self, event):
        hub.notify(event)

    # request handler

    def playlistgetcontents(self, request):
        return self.networkchannel.request(request)
