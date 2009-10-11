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

import hub, events
import pcm
import decoder
from services.player import genericplayer
import services.playlist
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
        self.ao = ao.AudioDevice(aodevice, rate=rate, byte_format=4, options=options)

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
                    log.debug_traceback()
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

#
# wrapper class for playlistitems or songs
#

class decodedsong:
    def __init__(self, playlistitemorsong, rate, profiles):
        if isinstance(playlistitemorsong, services.playlist.playlistitem):
            self.song = playlistitemorsong.song
            self.playlistitem = playlistitemorsong
        else:
            self.song = playlistitemorsong
            self.playlistitem = None
        self.decodedsong = decoder.decodedsong(self.song, rate)
        self.replaygain = self.calculate_replaygain(["track"])

        # these method are handled by the decodedsong
        self.seekrelative = self.decodedsong.seekrelative
        self.playfaster = self.decodedsong.playfaster
        self.playslower = self.decodedsong.playslower
        self.resetplayspeed = self.decodedsong.resetplayspeed

    def __repr__(self):
        return "decodedsong(%r)" % repr(self.song)

    def read(self, size):
        # read decoded pcm stram and adjust for replaygain if necessary
        buff = self.decodedsong.read(size)
        if self.replaygain != 1:
            pcm.scale(buff, self.replaygain)
        return buff

    def succeedsonalbum(self, otherdecodedsong):
        " checks whether otherdeocedsong follows self on the same album "
        return (self.song.artist      and self.song.artist == otherdecodedsong.song.artist and
                self.song.album       and self.song.album == otherdecodedsong.song.album and
                self.song.tracknumber and otherdecodedsong.song.tracknumber and
                self.song.tracknumber == otherdecodedsong.song.tracknumber-1 )

    def calculate_replaygain(self, profiles):
       # the following code is adapted from quodlibet
       """Return the recommended Replay Gain scale factor.

       profiles is a list of Replay Gain profile names ('album',
       'track') to try before giving up. The special profile name
       'none' will cause no scaling to occur.
       """
       for profile in profiles:
           if profile is "none":
               return 1.0
           try:
               db = getattr(self.song, "replaygain_%s_gain" % profile)
               peak = getattr(self.song, "replaygain_%s_peak" % profile)
           except AttributeError:
               continue
           else:
               if db is not None and peak is not None:
                   scale = 10.**(db / 20)
                   if scale * peak > 1:
                       scale = 1.0 / peak # don't clip
                   return min(15, scale)
       else:
           return 1.0

    def rtime(self):
        " remaing playing time "
        return self.decodedsong.ttime - self.decodedsong.ptime

    def ptime(self):
        " playing time "
        return self.decodedsong.ptime



class player(genericplayer):

    def __init__(self, id, playlistid, autoplay, aodevice, aooptions, bufsize,
                 crossfading, crossfadingstart, crossfadingduration):
        self.rate = 44100
        self.SIZE = 4096
        self.volume = 1
        self._volume_scale = 0.005    # factor for logarthmic volume change

        # use C version of buffered audio device if present
        if bufferedao_present:
            self.audiodev = bufferedao.bufferedao(bufsize, self.SIZE, aodevice, byte_format=4, rate=self.rate, options=aooptions)
            # we have to start a new thread for the bufferedao device
            thread.start_new(self.audiodev.start, ())
            log.debug("bufferedao device opened")
        else:
            # create audio device thread
            self.audiodev = bufferedaudiodev(aodevice, aooptions, bufsize, self.rate, self.SIZE)
            self.audiodev.start()

        # songs currently playing
        self.decodedsongs = []

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
        self.decodedsongs = []
        self.audiodev.flush()
        self.audiodev.closedevice()

    def play(self):
        """decode songs and mix them together"""

        # unpause buffered ao if necessary
        self.audiodev.unpause()

        if len(self.decodedsongs) == 1:
            song = self.decodedsongs[0]
            buff = song.read(self.SIZE)
            if len(buff) > 0:
                if self.volume != 1:
                    pcm.scale(buff, self._volume_scale**(1-self.volume))
                self.audiodev.play(buff, len(buff))
            else:
                log.debug("internal player: song ends: %r (0 songs in queue)" % self.decodedsongs[0])
                del self.decodedsongs[0]

            # reset songtransition mode, but before possibly requesting a new song
            self.songtransitionmode = None

            if len(buff) == 0 or (self.crossfading and song.rtime() < self.crossfadingstart):
                self.requestnextsong()

        elif len(self.decodedsongs) == 2:
            if self.songtransitionmode == "crossfade":
                # perform crossfading
                buff1 = self.decodedsongs[0].read(self.SIZE)
                buff2 = self.decodedsongs[1].read(self.SIZE)

                if len(buff1) and len(buff2):
                    # normal operation: no song has ended
                    buff, self.crossfadingratio = pcm.mix(buff1, buff2,
                                                          self.crossfadingratio,
                                                          self.crossfadingrate)
                    if self.crossfadingratio >= 1:
                        self.crossfadingratio = 0
                        log.debug("internal player: song ends: %r (1 song in queue)" %
                              self.decodedsongs[0])
                        del self.decodedsongs[0]
                if len(buff1) == 0:
                    buff = buff2
                    self.crossfadingratio = 0
                    log.debug("internal player: song ends: %r (1 song in queue)" % self.decodedsongs[0])
                    del self.decodedsongs[0]
                if len(buff2) == 0:
                    buff = buff1
                    self.crossfadingratio = 0
                    log.debug("internal player: song ends: %r" % self.decodedsongs[-1])
                    del self.decodedsongs[-1]
                    log.debug("internal player: %d songs in queue" % len(self.decodedsongs))
            elif self.songtransitionmode == "gapkill":
                # just kill gap between songs
                buff = self.decodedsongs[0].read(self.SIZE)
                if len(buff) < self.SIZE:
                    log.debug("internal player: song ends: %r (1 song in queue)" % self.decodedsongs[0])
                    del self.decodedsongs[0]

                    buff2 = self.decodedsongs[0].read(self.SIZE)
                    if len(buff2) == 0:
                        log.debug("internal player: song ends: %r" % self.decodedsongs[0])
                        del self.decodedsongs[0]
                        log.debug("internal player: %d songs in queue" % len(self.decodedsongs))
                    else:
                        buff = buff + buff2
            else:
                # neither crossfading nor gap killing
                del self.decodedsongs[0]
                buff = self.decodedsongs[0].read(self.SIZE)

            if len(buff) > 0:
                if self.volume != 1:
                    pcm.scale(buff, self._volume_scale**(1-self.volume))
                self.audiodev.play(buff, len(buff))

        # update playbackinfo

        if len(self.decodedsongs) > 0:
            # determine which song is currently played
            # try to take the buffer length into account
            if self.songtransitionmode == "crossfade" and self.decodedsongs[-1].ptime()-self.audiodev.queuelen() >= 0:
                playingsong = self.decodedsongs[-1]
                self.playbackinfo.updatecrossfade(1)
            else:
                playingsong = self.decodedsongs[0]
                self.playbackinfo.updatecrossfade(0)

            time = int(max(playingsong.ptime()-self.audiodev.queuelen(), 0))

            self.playbackinfo.updatesong(playingsong.song)
            self.playbackinfo.updatetime(time)
        else:
            self.playbackinfo.stopped()

    def _playsong(self, song, manual):
        log.debug("internal player: new song: %r" % song)

        if self.ispaused():
            self._flushqueue()

        # we want maximally 2 songs in queue
        if len(self.decodedsongs) == 2:
            del self.decodedsongs[0]

        try:
            self.decodedsongs.append(decodedsong(song, self.rate, ["track"]))
            if self.crossfading:
                self.songtransitionmode = "crossfade"
                # Check whether two songs come after each other on an
                # album In such a case, we don't want to crossfade.  If,
                # however, the user has requested the song change (via
                # playerforward), we do want crossfading.
                if not manual and len(self.decodedsongs) == 2:
                    if self.decodedsongs[0].succeedsonalbum(self.decodedsongs[1]):
                        self.songtransitionmode = "gapkill"
                        log.debug("internal player: don't crossfade successive songs.")
        except (IOError, RuntimeError):
            log.warning(_('failed to open song "%r"') % str(song.url))

        log.debug("internal player: %d songs in queue" % len(self.decodedsongs))

    def _playerpause(self):
        self.audiodev.pause()

    def _playerstop(self):
        self._flushqueue()

    def _playerseekrelative(self, seconds):
        if len(self.decodedsongs) == 0:
            return
        if len(self.decodedsongs) == 2:
            # we refuse to seek backward during crossfading
            if seconds < 0:
                return
            del self.decodedsongs[0]
        song = self.decodedsongs[0]
        song.seekrelative(seconds)
        self.audiodev.flush()

    def _player_change_volume_relative(self, volume_adj):
        self.volume = max(0, min(1, self.volume + volume_adj/100.0))
        hub.notify(events.player_volume_changed(self.id, self.volume))

    def _playerplayfaster(self):
        if self.decodedsongs:
            self.decodedsongs[0].playfaster()

    def _playerplayslower(self):
        if self.decodedsongs:
            self.decodedsongs[0].playslower()

    def _playerspeedreset(self):
        if self.decodedsongs:
            self.decodedsongs[0].resetplayspeed()

    def _playerreleasedevice(self):
        self.audiodev.closedevice()

    def _playerquit(self):
        self.audiodev.quit()
