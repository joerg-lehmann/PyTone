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

import curses, time

import config
import events, hub
import playlist
import statusbar
import window

from helper import formattime

class playlistwin(window.window):
    def __init__(self,  screen, layout, channel, playerid):
        self.channel = channel
        self.keybindings = config.keybindings.playlistwindow
        self.songformat = config.playlistwindow.songformat
        h, w, y, x, border = layout
        window.window.__init__(self,
                               screen, h, w, y, x,
                               config.colors.playlistwindow,
                               _("Playlist"),
                               border, config.playlistwindow.scrollbar)

        # Immediately remove focus from playlist window in order to
        # prevent wrong selectionchanged events being issued, which
        # would lead to playing the first song in the playlist on the
        # second player (if configured)
        self.bottom()

        self.playlist = playlist.playlist(self, playerid)

        self.channel.subscribe(events.keypressed, self.keypressed)
        self.channel.subscribe(events.mouseevent, self.mouseevent)
        self.channel.subscribe(events.focuschanged, self.focuschanged)

    def updatestatusbar(self):
        sbar = []
        if self.playlist.selected is not None:
            sbar += statusbar.generatedescription("playlistwindow", "deleteitem")
            sbar += statusbar.separator
            sbar += statusbar.generatedescription("playlistwindow", "moveitemup")
            sbar += statusbar.separator
            sbar += statusbar.generatedescription("playlistwindow", "moveitemdown")
            sbar += statusbar.separator

        sbar += statusbar.generatedescription("playlistwindow", "activatefilelist")
        hub.notify(events.updatestatusbar(0, sbar))

    def updatescrollbar(self):
        self.drawscrollbar(self.playlist.top, len(self.playlist))

    def resize(self, layout):
        h, w, y, x, self.border = layout
        window.window.resize(self, h, w, y, x)
        self.playlist._updatetop()
        if not self.hasfocus():
            self.playlist._recenter()

    def activatefilelist(self):
        # before recentering we remove the focus from the playlist in order
        # to prevent wrong songchanged events being issued (which would lead to
        # wrong songs being played on the secondary player)
        self.bottom()
        self.playlist._recenter()
        hub.notify(events.activatefilelist())

    # event handlers

    def keypressed(self, event):
        if self.hasfocus():
            key = event.key

            if key in self.keybindings["selectnext"]:
                self.playlist.selectnext()
            elif key in self.keybindings["selectprev"]:
                self.playlist.selectprev()
            elif key in self.keybindings["selectnextpage"]:
                self.playlist.selectnextpage()
            elif key in self.keybindings["selectprevpage"]:
                self.playlist.selectprevpage()
            elif key in self.keybindings["selectfirst"]:
                self.playlist.selectfirst()
            elif key in self.keybindings["selectlast"]:
                self.playlist.selectlast()
            elif key in self.keybindings["activatefilelist"]:
                self.activatefilelist()
            elif key in self.keybindings["moveitemup"]:
                self.playlist.moveitemup()
            elif key in self.keybindings["moveitemdown"]:
                self.playlist.moveitemdown()
            elif key in self.keybindings["deleteitem"]:
                self.playlist.deleteselected()
            elif key in self.keybindings["playselectedsong"]:
                self.playlist.playselected()
            elif key in self.keybindings["shuffle"]:
                hub.notify(events.playlistshuffle())
            elif key in self.keybindings["rescan"]:
                self.playlist.rescanselection()
            elif ord("0")<=key<=ord("5"):
                self.playlist.rateselection(key-ord("1")+1)
            elif key in self.keybindings["filelistjumptoselectedsong"]:
                self.playlist.filelistjumptoselected()
                self.activatefilelist()
            else:
                return

            self.update()
            raise hub.TerminateEventProcessing

    def mouseevent(self, event):
        if self.enclose(event.y, event.x):
            y, x = self.stdscrtowin(event.y, event.x)
            self.top()

            if event.state & curses.BUTTON1_CLICKED:
                if x==self.ix+self.iw and self.hasscrollbar:
                    scrollbarbegin, scrollbarheight = self.scrollbardimensions(self.playlist.top,
                                                                               len(self.playlist))
                    if y==self.iy+1:
                        self.playlist.selectprev()
                    elif y==self.iy+self.ih-2:
                        self.playlist.selectnext()
                    elif self.iy<y<scrollbarbegin:
                        self.playlist.selectprevpage()
                    elif scrollbarbegin+scrollbarheight<=y<self.iy+self.ih-2:
                        self.playlist.selectnextpage()
                else:
                    self.playlist.selectbylinenumber(y-1)
            elif event.state & curses.BUTTON1_DOUBLE_CLICKED:
                self.playlist.selectbylinenumber(y-1)
            elif event.state & curses.BUTTON3_CLICKED:
                pass
            else:
                return

            self.update()
            raise hub.TerminateEventProcessing

    def focuschanged(self, event):
        if self.hasfocus():
            hub.notify(events.selectionchanged(self.playlist.getselected()))
        self.update()

    # window update method

    def update(self):
        if self.playlist.autoplaymode == "repeat":
            autoplaymode = " [%s]" % _("Repeat")
        elif self.playlist.autoplaymode == "random":
            autoplaymode = " [%s]" % _("Random")
        else:
            autoplaymode = ""
        self.settitle("%s (-%s/%s)%s" % ( _("Playlist"),
                                        formattime((self.playlist.ttime-
                                                    self.playlist.ptime)),
                                        formattime(self.playlist.ttime),
                                        autoplaymode))

        window.window.update(self)
        if self.hasfocus():
            self.updatestatusbar()

        for i in range(self.playlist.top, self.playlist.top+self.ih):
            attr = curses.A_NORMAL

            if i<len(self.playlist):
                item = self.playlist[i]
                if item.playstarttime is not None:
                    h, m, s = time.localtime(item.playstarttime)[3:6]
                else:
                    h = m = s = 0
                adddict = {"playstarthours":   h,
                           "playstartminutes": m,
                           "playstartseconds": s}
                name = item.song.format(self.songformat, adddict=adddict)
                if self.playlist.playingitem and item is self.playlist.playingitem:
                    if self.playlist.selected==i and self.hasfocus():
                        attr = self.colors.selected_playingsong
                    else:
                        attr = self.colors.playingsong
                elif item.hasbeenplayed():
                    if i==self.playlist.selected and self.hasfocus():
                        attr = self.colors.selected_playedsong
                    else:
                        attr = self.colors.playedsong
                else:
                    if i==self.playlist.selected and self.hasfocus():
                        attr = self.colors.selected_unplayedsong
                    else:
                        attr = self.colors.unplayedsong
            else:
                name = ""
            self.addnstr(i-self.playlist.top+self.iy, self.ix, name.ljust(self.iw)[:self.iw], self.iw, attr)

        self.updatescrollbar()

        # move cursor to the right position in order to make it more
        # easy for users of Braille displays to track the current
        # position/selection
	if self.hasfocus() and self.playlist.selected is not None:
	    self.win.move(self.playlist.selected-self.playlist.top+1, 1)
