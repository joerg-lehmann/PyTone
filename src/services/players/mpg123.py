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
import os.path
import fcntl
import re
import string
import time

import log
import services.playlist
import hub,requests

from services.player import genericplayer

def makeNonBlocking(fd):
    fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)

startpattern = re.compile(r"^@R MPG123 *[-0-9a-zA-Z\s_]*$")

class player(genericplayer):
    def __init__(self, id, playlistid, autoplay, cmdline):
        self.cmdline = cmdline
        self.initmpg123()
        genericplayer.__init__(self, id, playlistid, autoplay)

    def initmpg123(self):
        """start new mpg123 process"""
        self.pstdin, self.pstdout = os.popen4(self.cmdline + " -R -")
        startline = self.pstdout.readline()
        if not re.match(startpattern, startline):
            raise RuntimeError("cannot initialize player")
        makeNonBlocking(self.pstdout.fileno())

    def closempg123(self):
        """terminate running mpg123 process"""
        if self.pstdin:
            self.pstdin.close()
        if self.pstdout:
            self.pstdout.close()

    def sendmpg123(self, command):
        """send command to mpg123 process"""
        try:
            self.pstdin.write("%s\n" % command)
            self.pstdin.flush()
        except IOError, error:
            # broken pipe => restart player
            if error[0]==32:
                self.closempg123()
                self.initmpg123()
                self.playbackinfo.stopped()
                self.pstdin.write("%s\n" % command)
            else:
                raise

    def receivempg123(self):
        """receive command from mpg123 process"""
        try:
            return self.pstdout.readline()
        except (ValueError, IOError):
            return ""
        

    def play(self):
        """play songs"""
        
        r = self.receivempg123()

        if r=="":
            time.sleep(0.1)
            # we just want to tease mpg123 a bit to check if it is still
            # alive
            self.sendmpg123("")
        elif r.startswith("@F"): 
            pframes, lframes, ptime, ltime = string.split(r[3:])[:4]
            ptime = int(float(ptime))
            self.playbackinfo.updatetime(ptime)
        elif r.startswith("@P"):
            if self.playbackinfo.isplaying() and r[3]=="0":
                self.playbackinfo.stopped()
                self.requestnextsong()
        elif r.startswith("@S"): 
            ( version, layer, samplerate, mode, modeextension,
              bytesperframe, channels, copyrighted, crcprotected, emphasis, bitrate ) = string.split(r[3:])[:11]
            self.framespersecond = 1000.0 / 8 * int(bitrate) / int(bytesperframe)
                    
    def _playsong(self, playlistitemorsong, manual):
        """play event.song next"""
        path = None
        if isinstance( playlistitemorsong, services.playlist.playlistitem ):
            url = playlistitemorsong.song.url
            if url.startswith("file://"):
                dbstats = hub.request(requests.getdatabasestats(playlistitemorsong.song.songdbid))
                path = os.path.join(dbstats.basedir, url[7:])
            else:
                path = url
        else:
            log.warning("mpg123 player: song %s not a playlistitem. Not added!" % repr( playlistitemorsong) )
            return
        self.sendmpg123("L %s" % path)
        self.framespersecond = None
        self.playbackinfo.updatesong(song, "")

    def _playerunpause(self):
        """unpause playing"""
        self.sendmpg123("P")
        # delete messages coming from mpg123
        time.sleep(0.1)
        while self.receivempg123()!="":
            pass
        self.playbackinfo.playing()

    def _playerpause(self):
        """pause playing"""
        self.sendmpg123("P")
        # delete messages coming from mpg123
        time.sleep(0.1)
        while self.receivempg123()!="":
            pass
        self.playbackinfo.paused()

    def _playerseekrelative(self, seconds):
        if self.framespersecond:
            self.sendmpg123("J %+d" % int(seconds * self.framespersecond))

    def _playerstop(self):
        """stop playing"""
        self.sendmpg123("S")
        # delete messages coming from mpg123
        time.sleep(0.1)
        while self.receivempg123()!="":
            pass
        self.playbackinfo.stopped()

    def _playerquit(self):
        self.sendmpg123("Q")
        self.closempg123()
