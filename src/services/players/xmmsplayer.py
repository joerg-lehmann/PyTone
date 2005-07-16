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

import os
import time
import xmms.control

from services.player import genericplayer

# Note: the implementation xmms player is a bit hackish,
# so don't look too close. At many places, sleeps have
# been interted to get it working, so as I said...

class player(genericplayer):
    def __init__(self, id, playlistid, autoplay, session=0, noqueue=0):
        self.session = session
        self.noqueue = noqueue

        # a mapping path -> song
        self.songs = {} 
        self.initxmms()
        
        genericplayer.__init__(self, id, playlistid, autoplay)

    def initxmms(self):
        if not xmms.control.is_running(self.session):
            abs_prog_name = xmms.control._find_and_check_executable("xmms")
            if not abs_prog_name:
                raise xmms.control.ExecutableNotFound("can't find XMMS executable")
            os.system(abs_prog_name + " >/dev/null 2>/dev/null &")
            while not xmms.control.is_running(self.session):
                time.sleep(0.2)

        xmms.control.playlist_clear(self.session)
        xmms.control.main_win_toggle(0, self.session)
        xmms.control.pl_win_toggle(0, self.session)
        xmms.control.eq_win_toggle(0, self.session)

    # event handler

    def play(self):
        if xmms.control.is_playing(self.session):
            pos = xmms.control.get_playlist_pos(self.session)
            # title = xmms.control.get_playlist_title(pos, self.session)
            # ttime = xmms.control.get_playlist_time(pos, self.session)
            # ptime = xmms.control.get_output_time(self.session)
            # self.playbackinfo = (title, int(ptime/1000), int(ttime/1000))
            path = xmms.control.get_playlist_file(pos, self.session)
            song = self.songs[path]
            ptime = xmms.control.get_output_time(self.session)/1000
            self.playbackinfo.updatesong(song)
            self.playbackinfo.updatetime(ptime)

            # fill up xmms playlist if necessary
            if song.length-ptime<20 and xmms.control.get_playlist_length()<2: 
                self.requestnextsong()
            if pos>0:
                path = xmms.control.get_playlist_file(0, self.session)
                xmms.control.playlist_delete(0, self.session)
                del self.songs[path]
        else:
            self.playbackinfo.updatesong(None)

        time.sleep(0.1)

    def _playsong(self, song, manual):
        if self.noqueue:
            xmms.control.playlist_clear(self.session)
            self.songs = {}
            
        self.songs[song.path] = song
        xmms.control.playlist_add((song.path,), self.session)

        if not xmms.control.is_playing():
            xmms.control.play(self.session)
            # wait a little, so that xmms can start playing
            # and we don't request another song...
            time.sleep(0.5)

    def _playerstart(self):
        # before we start playing, we clear the playlist
        xmms.control.playlist_clear(self.session)
        self.songs = {}

    def _playerpause(self):
        # before we start playing, we clear the playlist
        xmms.control.pause(self.session)

    def _playerunpause(self):
        # before we start playing, we clear the playlist
        xmms.control.play(self.session)

    def _playerseekrelative(self, seconds):
        ptime = xmms.control.get_output_time(self.session)
        pos = xmms.control.get_playlist_pos(self.session)
        ttime = xmms.control.get_playlist_time(pos, self.session)
        time = min(max(ptime + int(seconds * 1000), 0), ttime)
        xmms.control.jump_to_time(time, self.session)
    
    def _playerstop(self):
        xmms.control.playlist_clear(self.session)
        self.songs = {}

    def playernext(self, event):
        if event.playerid==self.id:
            if xmms.control.is_playing(self.session):
                self.requestnextsong()
                # wait a little for the other threads, uuh...
                time.sleep(1)
                self.channel.process()
                time.sleep(0.1)
            xmms.control.playlist_next(self.session)

    def _playerquit(self):
        xmms.control.quit(self.session)

