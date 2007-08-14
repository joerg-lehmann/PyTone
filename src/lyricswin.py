# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2006, 2007 Jörg Lehmann <joerg@luga.de>
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

import config
import item
import services.playlist
import events
import messagewin
import encoding

class lyricswin(messagewin.messagewin):

    def __init__(self, screen, maxh, maxw, channel):
        messagewin.messagewin.__init__(self, screen, maxh, maxw, channel,
                                       config.colors.lyricswindow,
                                       _("Lyrics"), [],
                                       config.lyricswindow.autoclosetime)
        self.lyrics = _("No lyrics")
        channel.subscribe(events.selectionchanged, self.selectionchanged)

    def _outputlen(self, width):
        try:
            return len(self.lyrics[0][2].split("\n"))
        except IndexError:
            return 1

    def showitems(self):
        self.clear()
        try:
            for lno, line in enumerate(self.lyrics[0][2].split("\n")[self.first:self.first+self.ih]):
                line = encoding.encode(line).strip().center(self.iw)
                self.addnstr(self.iy+lno, self.ix, line, self.iw, self.colors.content)
        except IndexError:
            pass

    def selectionchanged(self, event):
        if isinstance(event.item, item.song):
            song = event.item
        elif isinstance(event.item, services.playlist.playlistitem):
            song = event.item.song
        else:
             self.settitle(_("Lyrics"))
             self.lyrics = _("No song selected")
             return
        self.settitle("%s - %s - %s" % (song.artist, song.album, song.title))
        if song.lyrics:
            self.lyrics = song.lyrics
        else:
            self.lyrics = _("No lyrics")
