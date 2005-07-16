# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003 Jörg Lehmann <joerg@luga.de>
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

import copy, time

import events, hub, requests
import services.playlist
import service

def initplayer(id, config):
    """ initialize player with id defined by config
    return id (or None if player is turned off)
    """

    # only the first player has a playlist
    if id == "main":
        playlistid = "main"
    else:
        playlistid = None

    type = config.type
    if type=="off":
        return None
    elif type=="internal":
        import players.internal
        driver = config.driver
        if driver in ("alsa09", "alsa"):
            aooptions = {"dev": config.device}
        elif driver=="oss":
            aooptions = {"dsp": config.device}
        elif driver=="sun":
            aooptions = {"dev": config.device}
        else:
            aooptions = {}
        # add options given by user in config file
        for aooption in config.aooptions.split():
            key, value = aooption.split("=")
            aooptions[key] = value
        try:
            p = players.internal.player(id,
                                        playlistid,
                                        autoplay=config.autoplay,
                                        aodevice=driver,
                                        aooptions=aooptions,
                                        bufsize=config.bufsize,
                                        crossfading=config.crossfading,
                                        crossfadingstart=config.crossfadingstart,
                                        crossfadingduration=config.crossfadingduration,
                                        )
        except:
            raise RuntimeError("Cannot initialize %s player: type=internal, device=%s" % (id, config.device))
    elif type=="xmms":
        import players.xmmsplayer
        try:
            p = players.xmmsplayer.player(id,
                                          playlistid,
                                          autoplay=config.autoplay,
                                          session=config.session,
                                          noqueue=config.noqueue)
        except:
            raise RuntimeError("Cannot initialize %s player: type=xmms, session=%d" % (id, config.session))
    elif type=="mpg123":
        import players.mpg123
        try:
            p = players.mpg123.player(id,
                                      playlistid,
                                      autoplay=config.autoplay,
                                      cmdline=config.cmdline)

        except:
            raise RuntimeError("Cannot initialize %s player: type=mpg123, cmdline=%s" % (id, config.cmdline))
    elif type=="remote":
        import players.remote
        try:
            p = players.remote.player(id, playlistid, config.networklocation)
        except:
            raise
            raise RuntimeError("Cannot initialize %s player: type=remote, location=%s" % (id, config.networklocation))
        
    p.setName("player thread (id=%s)" % id)
    p.start()

    if type != "remote" and id == "main":
        services.playlist.initplaylist(id, id, id)

    return id

# player states

STOP     = 0
PAUSE    = 1
PLAY     = 2

class playbackinfo:
    
    """ class for storage of playback information

    This class serves as a means of communication between the
    actual players and the player control logic 

    """

    def __init__(self, playerid, state=STOP, song=None, time=0, crossfade=False):
        """ 

        playerid:  player which this playbackinfo instance refers to
        state:     player state (STOP, PAUSE, PLAY)
        song:      song currently played (or None, if player is not playing)
        time:      position in seconds in the song
        crossfade: crossfade in progress
        """
        self.playerid = playerid
        self.state = state
        self.song = song
        self.time = time
        self.crossfade = crossfade

    def __cmp__(self, other):
        return (cmp(self.playerid, other.playerid) or
                cmp(self.state, other.state) or
                cmp(self.song, other.song) or
                cmp(self.time, other.time) or
                cmp(self.crossfade, other.crossfade))

    def __str__(self):
        s = "player %s " % `self.playerid`
        if self.state==STOP:
            s = s + "stopped"
        elif self.state==PAUSE:
            s = s + "paused"
        elif self.state==PLAY:
            s = s + "playing"
        s = s + " song: "
        if self.song:
            s = s + "%s at time %f" % ( `self.song`, self.time)
        else:
            s = s + "None"
        if self.crossfade:
            s = s+ " (crossfading)"
        return s

    def updatesong(self, song):
        """ update song and reset time """
        self.song = song
        self.time = 0

    def stopped(self):
        self.state = STOP
        self.song = None
        self.time = 0
        self.crossfade = False

    def paused(self):
        self.state = PAUSE

    def playing(self):
        self.state = PLAY

    def updatetime(self, time):
        self.time = time

    def updatecrossfade(self, crossfade):
        self.crossfade = crossfade

    def isplaying(self):
        return self.state == PLAY

    def ispaused(self):
        return self.state == PAUSE

    def isstopped(self):
        return self.state == STOP

    def iscrossfading(self):
        return self.crossfade and not self.state == STOP


class genericplayer(service.service):
    def __init__(self, id, playlistid, autoplay):
        """create a new player
        
        id:         the player id
        playlistid: playlist responsible for feeding player with songs. Set to None, if
                    there is no playlist for the player.
        autoplay:   should the player start automatically, if a song is in the playlist
                    and it has not been stopped explicitely by the user
                    
        """
        service.service.__init__(self, "player %s" % id, daemonize=True)
        self.id = id
        self.autoplay = autoplay
        self.playlistid = playlistid
        
        # if wantplay != autoplay, the user has requested a player stop and thus
        # autoplay is effectively turned off, until the player is restarted again
        self.wantplay = autoplay

        # the playbackinfo structure describes the current player state
        self.playbackinfo = playbackinfo(self.id)

        # old playbackinfo, used to detect changes of the player state
        self.oplaybackinfo = copy.copy(self.playbackinfo)

        self.channel.subscribe(events.playerstart, self.playerstart)
        self.channel.subscribe(events.playerpause, self.playerpause)
        self.channel.subscribe(events.playertogglepause, self.playertogglepause)
        self.channel.subscribe(events.playerstop, self.playerstop)
        self.channel.subscribe(events.playernext, self.playernext)
        self.channel.subscribe(events.playerprevious, self.playerprevious)
        self.channel.subscribe(events.playerseekrelative, self.playerseekrelative)
        self.channel.subscribe(events.playerplaysong, self.playerplaysong)
        self.channel.subscribe(events.playerratecurrentsong, self.playerratecurrentsong)
        self.channel.supply(requests.getplaybackinfo, self.getplaybackinfo)

    def work(self):
        if self.isplaying():
            self.play()


        # request a new song, if none is playing and the player wants to play
        if self.isstopped() and self.wantplay:
            self.requestnextsong()

        # release player device if there is nothing to play
        if not self.isplaying():
            self._playerreleasedevice()

        # process incoming events
        self.channel.process()
        
        # and notify the rest of any changes in the playback status
        self.updatestatus()
        # Now the queue of all pending events has been
        # cleared. Depending on the player status we can now wait for
        # further incoming events.
        if not self.isplaying():
            # We sleep a little bit to prevent being overly active
            # when the event channel is spilled by messages
            time.sleep(0.2)
            # In this case, we can safely block since we will be waked
            # up by any message on the event channel. Thus, event if
            # we want to request a new song, we can rely on an event
            # signaling the addition of a new song to the playlist
            self.channel.process(block=True)

    def play(self):
        """play songs

        this method has to be implemented by specialized classes"""
        pass

    def updatestatus(self):
        """notify interested parties of changes in player status"""
        if self.oplaybackinfo != self.playbackinfo:
            self.oplaybackinfo = copy.copy(self.playbackinfo)
            hub.notify(events.playbackinfochanged(self.playbackinfo))

    def requestnextsong(self, manual=False, previous=False):
        """request next song from playlist and play it"""
        if self.playlistid is not None:
            nextsong = hub.request(requests.requestnextsong(self.playlistid, previous))
            self.playsong(nextsong, manual)

    def playsong(self, song, manual):
        """add song to playlist and mark song played, if song is not None

        manual indicates whether the user has requested the song manually
        """
        if song:
            self._playsong(song, manual)
            self.playbackinfo.playing()

    def isstopped(self):
        return self.playbackinfo.state == STOP

    def ispaused(self):
        return self.playbackinfo.state == PAUSE

    def isplaying(self):
        return self.playbackinfo.state == PLAY

    def _playsong(self, song, manual):
        """add song to playlist

        manual indicates whether the user has requested the song manually

        this method has to be implemented by specialized classes"""
        pass

    def _playerstart(self):
        """prepare player for playing

        this method has to be implemented by specialized classes"""
        pass

    def _playerpause(self):
        """pause player 

        this method has to be implemented by specialized classes"""
        pass

    def _playerunpause(self):
        """restart player after pause

        this method has to be implemented by specialized classes"""
        pass

    def _playerstop(self):
        """stop playing

        this method has to be implemented by specialized classes"""
        pass
    
    def _playerseekrelative(self, seconds):
        """seek by the given number of seconds in file (relative to current position)

        this method has to be implemented by specialized classes"""
        pass

    def _playerreleasedevice(self):
        """temporarily release audio device 

        this method has to be implemented by specialized classes"""
        pass

    def _playerquit(self):
        """quit player

        this method has to be implemented by specialized classes"""
        pass

    # event handlers

    def playerstart(self, event):
        """start playing"""
        if event.playerid == self.id:
            if self.ispaused():
                self._playerunpause()
            elif self.isstopped():
                self.wantplay = self.autoplay
                self._playerstart()
                self.requestnextsong()
            self.playbackinfo.playing()

    def playerpause(self, event):
        """start/pause player"""
        if event.playerid == self.id:
            if self.isplaying():
                self.playbackinfo.paused()
                self._playerpause()

    def playertogglepause(self, event):
        """start/pause player"""
        if event.playerid == self.id:
            if self.isplaying():
                self.playbackinfo.paused()
                self._playerpause()
            elif self.ispaused():
                self.playbackinfo.playing()
                self._playerunpause()

    def playerstop(self, event):
        """stop playing"""
        if event.playerid == self.id:
            self.wantplay = False
            self.playbackinfo.stopped()
            self._playerstop()

    def playernext(self, event):
        """immediately play next song"""
        if event.playerid == self.id:
            self.requestnextsong(manual=1)

    def playerprevious(self, event):
        """immediately play previous song"""
        if event.playerid == self.id:
            self.requestnextsong(manual=1, previous=1)

    def playerseekrelative(self, event):
        """seek by event.seconds in file (relative to current position """
        if event.playerid == self.id:
            self._playerseekrelative(event.seconds)

    def playerplaysong(self, event):
        """play event.song next"""
        if event.playerid == self.id:
            self.playsong(event.song, manual=1)

    def playerratecurrentsong(self, event):
        """play event.song next"""
        if event.playerid == self.id and self.playbackinfo.song and 1 <= event.rating <= 5:
            self.playbackinfo.song.rate(event.rating)

    def quit(self, event):
        """quit player"""
        service.service.quit(self, event)
        self._playerquit()

    # request handlers

    def getplaybackinfo(self, request):
        if self.id != request.playerid:
            raise hub.DenyRequest
        else:
            return self.playbackinfo
