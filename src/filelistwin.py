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

import curses

import config
import events, hub
import item
import filelist
import statusbar
import window
import encoding


class filelistwin(window.window):
    def __init__(self, screen, layout, channel, songdbids):
        self.channel = channel
        self.keybindings = config.keybindings.filelistwindow
        self.songdbids = songdbids

        # last search string
        self.searchstring = None
        # list of selections during incremental search
        self.searchpositions = []

        # last song added to playlist
        self.lastadded = None

        h, w, y, x, border = layout

        window.window.__init__(self,
                               screen, h, w, y, x,
                               config.colors.filelistwindow,
                               "MP3s",
                               border, config.filelistwindow.scrollbar)

        self.items = filelist.filelist(self, self.songdbids)

        self.channel.subscribe(events.keypressed, self.keypressed)
        self.channel.subscribe(events.mouseevent, self.mouseevent)
        self.channel.subscribe(events.focuschanged, self.focuschanged)

    def sendmessage(self, message):
        hub.notify(events.statusbar_showmessage(message))
        # allow message to be processed
        self.channel.process()

    def updatestatusbar(self):
        sbar = []
        if len(self.items.shistory)>0:
            sbar += statusbar.generatedescription("filelistwindow", "dirup")
            sbar += statusbar.separator
        if self.items.isdirselected():
            sbar += statusbar.generatedescription("filelistwindow", "dirdown")
            sbar += statusbar.separator
            sbar += statusbar.generatedescription("filelistwindow", "adddirtoplaylist")
            sbar += statusbar.separator
        elif self.items.issongselected():
            sbar += statusbar.generatedescription("filelistwindow", "addsongtoplaylist")
            sbar += statusbar.separator

        sbar += statusbar.generatedescription("filelistwindow", "activateplaylist")
        hub.notify(events.statusbar_update(0, sbar))

    def updatescrollbar(self):
        self.drawscrollbar(self.items.top, len(self.items))

    def searchhandler(self, searchstring, key):
        if key == curses.KEY_BACKSPACE:
            if self.searchpositions:
                self.items.selectbynr(self.searchpositions.pop())
        elif key in self.keybindings["repeatsearch"]:
            self.items.selectbyregexp(searchstring, includeselected=False)
        elif key == ord("\n"):
            self.searchpositions = []
            self.searchstring = searchstring
            hub.notify(events.activatefilelist())
        elif key == 1023:
            if self.searchpositions:
                self.items.selectbynr(self.searchpositions.pop())
            self.searchpositions = []
            self.searchstring = searchstring
            hub.notify(events.activatefilelist())
        else:
            self.searchpositions.append(self.items.selected)
            self.items.selectbyregexp(searchstring)
            # We explicitely issue a selectionchanged event because the
            # selectbyregexp doesn't do this due to the focus being on the
            # searchstring input window
        hub.notify(events.selectionchanged(self.items.getselected()))
        self.update()

    def focus_on_handler(self, searchstring, key):
        if key == ord("\n") and searchstring:
           self.items.focus_on(searchstring)

    def isclickonstring(self, y, x):
        """ check whether a click was on a string or not """
        while x < self.ix+self.iw:
            if self.win.inch(y, x) & 0xFF!=32:
                return 1
            x += 1
        return 0

    def resize(self, layout):
        h, w, y, x, self.border = layout
        window.window.resize(self, h, w, y, x)
        self.items._updatetop()

    # event handler

    def keypressed(self, event):
        if self.hasfocus():
            key = event.key
            if key in self.keybindings["selectnext"]:
                self.items.selectnext()
            elif key in self.keybindings["selectprev"]:
                self.items.selectprev()
            elif key in self.keybindings["selectnextpage"]:
                self.items.selectnextpage()
            elif key in self.keybindings["selectprevpage"]:
                self.items.selectprevpage()
            elif key in self.keybindings["selectfirst"]:
                self.items.selectfirst()
            elif key in self.keybindings["selectlast"]:
                self.items.selectlast()
            elif key in self.keybindings["dirdown"] and \
                     self.items.isdirselected():
                self.items.dirdown()
            elif key in self.keybindings["dirup"]:
                self.items.dirup()
            elif key in self.keybindings["addsongtoplaylist"] and \
                     self.items.issongselected():
                songtoadd = self.items.getselected()
                if self.items.selected is not self.lastadded:
                    self.lastadded = self.items.selected
                    hub.notify(events.playlistaddsongs([songtoadd]))
                    self.items.selectrelative(+1)
            elif key in self.keybindings["adddirtoplaylist"] and \
                     self.items.isdirselected():
                itemtoadd = self.items.getselected()
                if self.items.selected is not self.lastadded:
                    self.lastadded = self.items.selected
                    self.items.insertrecursiveselection()
                    self.items.selectrelative(+1)
            elif key in self.keybindings["playselectedsong"] and \
                     self.items.issongselected():
                songtoplay = self.items.getselected()
                hub.notify(events.playlistaddsongtop(songtoplay))
            elif key in self.keybindings["activateplaylist"]:
                hub.notify(events.activateplaylist())
            elif key in self.keybindings["insertrandomlist"] and self.items.isdirselected():
                self.items.randominsertrecursiveselection()
            elif key in self.keybindings["repeatsearch"]:
                if self.searchstring:
                    self.items.selectbyregexp(self.searchstring, includeselected=False)
            elif key in self.keybindings["search"]:
                hub.notify(events.requestinput(_("Search"),
                                                      "",
                                                      self.searchhandler))
            elif key in self.keybindings["focus"]:
                hub.notify(events.requestinput(_("Focus on"),
                                                 "",
                                                 self.focus_on_handler))
            elif key in self.keybindings["rescan"]:
                self.items.rescanselection(force=True)
                self.items.selectrelative(+1)
            elif key in self.keybindings["toggledelete"]:
                self.items.toggledeleteselection()
            elif ord("a")<=key-1024<=ord("z") or ord("A")<=key-1024<=ord("Z") :
                self.items.selectbyletter(chr(key-1024))
            elif ord("0")<=key<=ord("5"):
                if self.items.rateselection(key-ord("1")+1):
                    self.items.selectrelative(+1)
            else:
                return

            if self.items.selected != self.lastadded:
                self.lastadded = None

            self.update()
            raise hub.TerminateEventProcessing

    def mouseevent(self, event):
        if self.enclose(event.y, event.x):
            y, x = self.stdscrtowin(event.y, event.x)
            self.top()

            if event.state & curses.BUTTON1_CLICKED:
                if x==self.ix+self.iw and self.hasscrollbar:
                    scrollbarbegin, scrollbarheight = self.scrollbardimensions(self.items.top,
                                                                               len(self.items))
                    if y==self.iy+1:
                        self.items.selectprev()
                    elif y==self.iy+self.ih-2:
                        self.items.selectnext()
                    elif self.iy<y<scrollbarbegin:
                        self.items.selectprevpage()
                    elif scrollbarbegin+scrollbarheight<=y<self.iy+self.ih-2:
                        self.items.selectnextpage()
                elif self.items.selectbylinenumber(y-self.iy) and \
                   self.isclickonstring(y, x) and \
                   self.items.isdirselected():
                    self.items.dirdown()
            elif event.state & curses.BUTTON1_DOUBLE_CLICKED:
                if self.items.selectbylinenumber(y-self.iy) and \
                   self.isclickonstring(y, x):
                    if self.items.issongselected():
                        songtoadd = self.items.getselected()
                        self.lastadded = None
                        hub.notify(events.playlistaddsongs([songtoadd]))
                    else:
                        self.lastadded = None
                        self.items.insertrecursiveselection()
            elif event.state & curses.BUTTON3_CLICKED:
                self.items.dirup()
            else:
                return

            self.update()
            raise hub.TerminateEventProcessing

    def focuschanged(self, event):
        if self.hasfocus():
            self.lastadded = None
            hub.notify(events.selectionchanged(self.items.getselected()))
        self.update()

    # window update method

    def update(self):
        self.settitle(self.items.selectionpath())
        window.window.update(self)

        if self.hasfocus():
            self.updatestatusbar()

        showselectionbar = self.hasfocus() or self.searchpositions

        for i in range(self.items.top, self.items.top+self.ih):
            attr = curses.A_NORMAL
            if i<len(self.items):
                aitem = self.items[i]
                name = self.items[i].getname()
                if isinstance(aitem, item.song):
                    if i==self.items.selected and showselectionbar:
                        attr = self.colors.selected_song
                    else:
                        attr = self.colors.song
                elif isinstance(aitem, (item.artist, item.album)):
                    if i==self.items.selected and showselectionbar:
                        attr = self.colors.selected_artist_album
                    else:
                        attr = self.colors.artist_album
                else:
                    if i==self.items.selected and showselectionbar:
                        attr = self.colors.selected_directory
                    else:
                        attr = self.colors.directory
            else:
                name = ""
            name = encoding.encode(name)
            self.addstr(i-self.items.top+self.iy, self.ix, name.ljust(self.iw)[:self.iw], attr)

        self.updatescrollbar()

        # move cursor to the right position in order to make it more
        # easy for users of Braille displays to track the current
        # position/selection
        if self.hasfocus() and self.items.selected is not None:
            self.win.move(self.items.selected-self.items.top+1, 1)

