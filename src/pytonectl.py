#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2003, 2004, 2007 Jörg Lehmann <joerg@luga.de>
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

import os, os.path, sys, getopt

##############################################################################
# gettext initialization.
##############################################################################

# We have to do this very early, before importing our modules. We
# assume that the locales lie in same dir as this module. This may not
# be the case, if the .mo files are installed at their proper
# location.

try:
    import gettext
    locallocaledir = os.path.join(os.path.dirname(sys.argv[0]), "../locale")
    gettext.install("PyTone", locallocaledir)
except:
    # Disable localization if there is any problem with the above.
    # This works around a problem with Python 2.1
    import __builtin__
    __builtin__.__dict__['_'] = lambda s: s

import network, events, requests, version, helper

#
# parse command line options
#

server = None
port = 1972
unixsocketfile = None
debugmode = False

def usage():
    print "pytonectl %s" % version.version
    print "Copyright (C) 2003, 2004 Jörg Lehmann <joerg@luga.de>"
    print "usage: pytonectl.py [options] command"
    print
    print "Possible options are:"
    print "   -h, --help:              show this help"
    print "   -s, --server <hostname>: connect to PyTone server on hostname"
    print "   -p, --port <portnumber>: connect to PyTone server on given port"
    print "   -f, --file <filename>:   connect to PyTone UNIX socket filename"
    print "   -d, --debug:             enable debug mode"
    print
    print "The supported commands are:"
    print "    getplayerinfo:                  show information on the song currently being played"
    print "    playerforward:                  play the next song in the playlist"
    print "    playerprevious:                 play the previous song in the playlist"
    print "    playerseekrelative <seconds>:   seek relative in the current song by the given number of seconds"
    print "    playerpause:                    pause the player"
    print "    playerstart:                    start/unpause the player"
    print "    playertogglepause:              pause the player, if playing, or play, if paused"
    print "    playerstop:                     stop the player"
    print "    playerratecurrentsong <rating>: rate the song currently being played (1<=rating<=5)"
    print "    playlistaddsongs <filenames>:   add files to end of playlist"
    print "    playlistaddsongtop <filename>:  play file immediately"
    print "    playlistclear:                  clear the playlist"
    print "    playlistdeleteplayedsongs:      remove all played songs from the playlist"
    print "    playlistreplay:                 mark all songs in the playlist as unplayed"
    print "    playlistshuffle:                shuffle the playlist"

try:
    opts, args = getopt.getopt(sys.argv[1:],
                               "hs:p:f:d",
                               ["help", "server=", "port=", "file=", "debug"])
except getopt.GetoptError:
    usage()
    sys.exit(2)

for o, a in opts:
    if o in ("-h", "--help"):
        usage()
        sys.exit()
    if o in ("-s", "--server"):
        server = a
    if o in ("-p", "--port"):
        port = int(a)
    if o in ("-f", "--file"):
        unixsocketfile = a
    if o in ("-d", "--debug"):
        debugmode = True

# initialize the debug file if necessary
import log, sys
if debugmode:
    log.debugfile = sys.stdout
    log.info("Debug mode enabled")

if server is not None and unixsocketfile is not None:
    print "Error: cannot connect both via network and unix sockets"
    sys.exit(2)
if server is None:
    if unixsocketfile is None:
        unixsocketfile =  os.path.expanduser("~/.pytone/pytonectl")
    networklocation = unixsocketfile
else:
    networklocation = server, port

try:
    channel = network.clientchannel(networklocation)
except Exception, e:
    print "Error: cannot connect to PyTone server: %s" % e
    sys.exit(2)

channel.start()

if len(args)==0:
    usage()
    sys.exit(2)
elif len(args)==1:
    if args[0]=="playerforward":
        channel.notify(events.playernext("main"))
    elif args[0]=="playerprevious":
        channel.notify(events.playerprevious("main"))
    elif args[0]=="playerpause":
        channel.notify(events.playerpause("main"))
    elif args[0]=="playerstart":
        channel.notify(events.playerstart("main"))
    elif args[0]=="playertogglepause":
        channel.notify(events.playertogglepause("main"))
    elif args[0]=="playerstop":
        channel.notify(events.playerstop("main"))
    elif args[0]=="playlistclear":
        channel.notify(events.playlistclear())
    elif args[0]=="playlistdeleteplayedsongs":
        channel.notify(events.playlistdeleteplayedsongs())
    elif args[0]=="playlistreplay":
        channel.notify(events.playlistreplay())
    elif args[0]=="playlistshuffle":
        channel.notify(events.playlistshuffle())
    elif args[0]=="getplayerinfo":
        playbackinfo = channel.request(requests.getplaybackinfo("main"))
        if playbackinfo.song:
            # we have to manually request the song metadata because there the main event and request hub is not correctly
            # initialized
            song_metadata = channel.request(requests.getsong_metadata(playbackinfo.song.songdbid, playbackinfo.song.id))
            print "%s - %s (%s/%s)" % ( song_metadata.artist,
                                        song_metadata.title,
                                        helper.formattime(playbackinfo.time),
                                        helper.formattime(song_metadata.length))
    else:
        usage()
        sys.exit(2)
else:
    if args[0]=="playerratecurrentsong" and len(args)==2:
        try:
            rating = int(args[1])
            if not 1<=rating<=5:
                raise
        except:
            usage()
            sys.exit(2)
        channel.notify(events.playerratecurrentsong("main", rating))
    if args[0]=="playerseekrelative" and len(args)==2:
        try:
            seconds = float(args[1])
        except:
            usage()
            sys.exit(2)
        channel.notify(events.playerseekrelative("main", seconds))
    elif args[0]=="playlistaddsongs":
        songs = [channel.request(requests.autoregisterer_queryregistersong("main", path)) for path in args[1:]]
        channel.notify(events.playlistaddsongs(songs))
    elif args[0]=="playlistaddsongtop" and len(args)==2:
        song = channel.request(requests.autoregisterer_queryregistersong("main", (args[1])))
        channel.notify(events.playlistaddsongtop(song))
    else:
        usage()
        sys.exit(2)

channel.quit()
