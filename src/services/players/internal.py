# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004 Jörg Lehmann <joerg@luga.de>
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

import Queue
import sys
import threading
import time

import pcm
import decoder
from services.player import genericplayer
import log

try:
    import bufferedao
    import thread
    bufferedao_present = True
except ImportError:
    bufferedao_present = False
    try:
        import ao
        ao_present = True
    except ImportError:
        ao_present = False
    try:
        import ossaudiodev
        ossaudiodev_present = False
    except ImportError:
        ossaudiodev_present = False
    

class aoaudiodev:
    def __init__(self, aodevice, rate, options):
        self.ao = ao.AudioDevice(aodevice, rate=rate, options=options)

    def play(self, buff, bytes):
        self.ao.play(buff, bytes)

    def close(self):
        # to close the ao audio device, we have to delete it...
        del self.ao 

# support for new ossaudiodev module of Python 2.3

class ossaudiodev:
    def __init__(self, device, rate):
        self.ossdevice = ossaudiodev.open(device, "w")
        if sys.byteorder == 'little':
            self.ossdevice.setfmt(ossaudiodev.AFMT_S16_LE)
        else:
            self.ossdevice.setfmt(ossaudiodev.AFMT_S16_BE)
        self.ossdevice.channels(2)
        self.ossdevice.speed(rate)

    def play(self, buff, bytes):
        self.ossdevice.write(buff)

    def close(self):
        self.ossdevice.close()


class bufferedaudiodev(threading.Thread):
    def __init__(self, aodevice, aooptions, bufsize, rate, SIZE):
        self.aodevice = aodevice
        self.aooptions = aooptions
        self.rate = rate
        self.SIZE = SIZE
        
        # initially, we do not open the audio device
        self.audiodev = None

        # output queue
        queuesize = 1024*bufsize/self.SIZE + 1
        self.queue = Queue.Queue(queuesize)
        
        self.done = False
        # wait if player thread is paused
        self.ispaused = False
        self.restart = threading.Event()
        threading.Thread.__init__(self)
        self.setDaemon(True)

    def opendevice(self):
        errorlogged = False
        while self.audiodev is None:
            try:
                if self.aodevice=="oss":
                    if ossaudiodev_present:
                        self.audiodev = ossaudiodev(self.aooptions["dsp"], self.rate)
                        log.debug("ossaudiodev audio device opened")
                    else:
                        self.audiodev = aoaudiodev(self.aodevice, rate=self.rate, options=self.aooptions)
                        log.debug("ao audio device opened")
                else:
                    self.audiodev = aoaudiodev(self.aodevice, rate=self.rate, options=self.aooptions)
                    log.debug("ao audio device opened")
            except Exception, e:
                if not errorlogged:
                    log.error(_('cannot open audio device: error "%s"') % e)
                    errorlogged = True
                time.sleep(1)

    def closedevice(self):
        if self.audiodev is not None:
            # we use self.audiodev = None as a marker for a closed audio device
            # To avoid race conditions we thus first have to mark the device as
            # closed before really closing it. Note that when we try to reopen the device
            # later, and it has not yet been closed, the opendevice method will retry
            # this 
            openaudiodev = self.audiodev
            self.audiodev = None
            openaudiodev.close()
            log.debug("audio device closed")

    def queuelen(self):
        """ return length of currently buffered PCM data in seconds"""
        return 1.0/4.0*self.queue.qsize()*self.SIZE/self.rate

    def run(self):
        while not self.done:
            try:
                if self.ispaused:
                    self.restart.wait()
                    self.restart.clear()
                buff, bytes = self.queue.get(1)
                if buff != 0 and bytes != 0:
                    audiodev = self.audiodev
                    while audiodev is None:
                        self.opendevice()
                        audiodev = self.audiodev
                    audiodev.play(buff, bytes)
            except:
                log.warning("exception occured in bufferedaudiodev")
                log.debug_traceback()

    def play(self, buff, bytes):
        self.queue.put((buff, bytes))

    def flush(self):
        while True:
            try:
                self.queue.get(0)
            except Queue.Empty:
                break

    def pause(self):
        self.ispaused = True
        self.closedevice()

    def unpause(self):
        if self.ispaused:
            self.ispaused = False
            self.restart.set()

    def quit(self):
        self.done = True
        self.flush()
        self.closedevice()
        self.restart.set()


class player(genericplayer):

    def __init__(self, id, playlistid, autoplay, aodevice, aooptions, bufsize,
                 crossfading, crossfadingstart, crossfadingduration):
        self.rate = 44100
        self.SIZE = 4096

        # use C version of buffered audio device if present
        if bufferedao_present:
            self.audiodev = bufferedao.bufferedao(bufsize, self.SIZE, aodevice, rate=self.rate, options=aooptions)
            # we have to start a new thread for the bufferedao device
            thread.start_new(self.audiodev.start, ())
            log.debug("bufferedao device opened")
        else:
            # create audio device thread
            self.audiodev = bufferedaudiodev(aodevice, aooptions, bufsize, self.rate, self.SIZE)
            self.audiodev.start()

        # songs currently playing
        self.songs = []

        self.crossfading = crossfading
        if self.crossfading:
            # crossfading parameters (all values in seconds and change/second, resp.)
            self.crossfadingduration = crossfadingduration
            self.crossfadingstart = crossfadingstart
            self.crossfadingratio = 0
            self.crossfadingrate = 1.0/self.rate/self.crossfadingduration

        # self.songtransitionmode determines the behaviour on transitions between two songs
        # possible values are "crossfade", "gapkill" and None (do nothing special)
        self.songtransitionmode = None

        genericplayer.__init__(self, id, playlistid, autoplay)

    def _flushqueue(self):
        """ delete internal player queue and flush audiodevice """
        self.songs = []
        self.audiodev.flush()
        self.audiodev.closedevice()

    def play(self):
        """decode songs and mix them together"""

        # unpause buffered ao if necessary
        self.audiodev.unpause()

        if len(self.songs) == 1:
            song = self.songs[0]
            buff = song.read(self.SIZE)
            if len(buff) > 0:
                self.audiodev.play(buff, len(buff))
            else:
                log.debug("internal player: song ends: %s (0 songs in queue)" % self.songs[0])
                del self.songs[0]
        
            # reset songtransition mode, but before possibly requesting a new song
            self.songtransitionmode = None

            if len(buff) == 0 or (self.crossfading and song.ttime-song.ptime < self.crossfadingstart):
                self.requestnextsong()

        elif len(self.songs) == 2:
            if self.songtransitionmode == "crossfade":
                # perform crossfading
                buff1 = self.songs[0].read(self.SIZE)
                buff2 = self.songs[1].read(self.SIZE)

                if len(buff1) and len(buff2):
                    # normal operation: no song has ended
                    buff, self.crossfadingratio = pcm.mix(buff1, buff2,
                                                          self.crossfadingratio,
                                                          self.crossfadingrate)
                    if self.crossfadingratio >= 1:
                        self.crossfadingratio = 0
                        log.debug("internal player: song ends: %s (1 song in queue)" %
                              self.songs[0])
                        del self.songs[0]
                if len(buff1) == 0:
                    buff = buff2
                    self.crossfadingratio = 0
                    log.debug("internal player: song ends: %s (1 song in queue)" % self.songs[0])
                    del self.songs[0]
                if len(buff2) == 0:
                    buff = buff1
                    self.crossfadingratio = 0
                    log.debug("internal player: song ends: %s" % self.songs[-1])
                    del self.songs[-1]
                    log.debug("internal player: %d songs in queue" % len(self.songs))
            elif self.songtransitionmode == "gapkill":
                # just kill gap between songs
                buff = self.songs[0].read(self.SIZE)
                if len(buff) < self.SIZE:
                    log.debug("internal player: song ends: %s (1 song in queue)" % self.songs[0])
                    del self.songs[0]

                    buff2 = self.songs[0].read(self.SIZE)
                    if len(buff2) == 0:
                        log.debug("internal player: song ends: %s" % self.songs[0])
                        del self.songs[0]
                        log.debug("internal player: %d songs in queue" % len(self.songs))
                    else:
                        buff = buff + buff2
            else:
                # neither crossfading nor gap killing
                del self.songs[0]
                buff = self.songs[0].read(self.SIZE)

            if len(buff) > 0:
                self.audiodev.play(buff, len(buff))

        # update playbackinfo

        if len(self.songs) > 0:
            # determine which song is currently played
            # try to take the buffer length into account
            if self.songtransitionmode == "crossfade" and self.songs[-1].ptime-self.audiodev.queuelen() >= 0:
                playingsong = self.songs[-1]
                self.playbackinfo.updatecrossfade(1)
            else:
                playingsong = self.songs[0]
                self.playbackinfo.updatecrossfade(0)

            time = int(max(playingsong.ptime-self.audiodev.queuelen(), 0))

            self.playbackinfo.updatesong(playingsong.song)
            self.playbackinfo.updatetime(time)
        else:
            self.playbackinfo.stopped()

    def _playsong(self, song, manual):
        log.debug("internal player: new song: %s" % song)

        if self.ispaused():
            self._flushqueue()

        # we want maximally 2 songs in queue
        if len(self.songs) == 2:
            del self.songs[0]

        try:
            self.songs.append(decoder.decodedsong(song, self.rate))
            if self.crossfading:
                self.songtransitionmode = "crossfade"
                # Check whether two songs come after each other on an
                # album In such a case, we don't want to crossfade.  If,
                # however, the user has requested the song change (via
                # playerforward), we do want crossfading.
                if not manual and len(self.songs) == 2:
                    song1 = self.songs[0].song
                    song2 = self.songs[1].song
                    # XXX no check for artist/album==UNKNOWN!
                    if (song1.artist == song2.artist and
                        song1.album == song2.album and
                        song1.tracknr != "" and song2.tracknr != "" and
                        int(song1.tracknr) == int(song2.tracknr)-1):
                        self.songtransitionmode = "gapkill"
                        log.debug("internal player: I don't crossfade successive songs.")
        except (IOError, RuntimeError):
            log.warning(_('failed to open song "%s"') % song.path)

        log.debug("internal player: %d songs in queue" % len(self.songs))

    def _playerpause(self):
        self.audiodev.pause()

    def _playerstop(self):
        self._flushqueue()

    def _playerseekrelative(self, seconds):
        if len(self.songs) == 0:
            return
        if len(self.songs) == 2:
            # we refuse to seek backward during crossfading
            if seconds < 0:
                return
            del self.songs[0]
        song = self.songs[0]
        song.seekrelative(seconds)
        self.audiodev.flush()

    def _playerreleasedevice(self):
        self.audiodev.closedevice()

    def _playerquit(self):
        self.audiodev.quit()
