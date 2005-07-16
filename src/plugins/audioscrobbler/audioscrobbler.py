# -*- coding: UTF-8 -*-
##############################################################################
#
# Copyright (c) 2004 Nicolas Évrard All Rights Reserved.
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

import events
import config
import log
import plugin
import scrobbler

# the configuration section [plugin.audioscrobbler] contains two options:
# username and password

class audioscrobblerconfig(config.configsection):
    username = config.configstring("")
    password = config.configstring("")


# sending of audioscrobbler information may take time, so we make this a
# separate thread by deriving from plugin.threadedplugin

class audioscrobblerplugin(plugin.threadedplugin):

    def init(self):
        self.scrobbler = scrobbler.Scrobbler(self.config.username, self.config.password)
        self.scrobbler.handshake()
        self.lastSong = None
        self.channel.subscribe(events.playbackinfochanged, self.playbackinfochanged)
        log.info("started audiscrobbler plugin")

    def playbackinfochanged(self, event):
        if not event.playbackinfo.isplaying():
            return
        song = event.playbackinfo.song
        # do not submit songs which are shorter than 30 seconds or longer than 30 minutes
        if song.length < 30 or song.length > 30*60:
            return
        # submit when the song playback is 50% complete or 240 seconds have been passed,
        # whatever comes first
        mintime = (song.length <= 480 and int(song.length/2)) or 240
        if ( event.playbackinfo.time >= mintime and song != self.lastSong):
            try:
                self.scrobbler.submit(song)
                log.debug("Audioscrobbler: submission of song '%s' successful" % song.path)
            except scrobbler.SubmissionError:
                log.error("Audioscrobbler: submission failed")
            except scrobbler.BadAuthError:
                log.error("Audioscrobbler: incorrect account information")
            self.lastSong = song
