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
import curses.panel
import events, hub
import config
import encoding
import log

class window:
    def __init__(self, screen,
                 h, w, y, x,
                 colors,
                 title=None,
                 border = 15,
                 hasscrollbar=0):
        self.screen = screen
        self.win = curses.newwin(h, w, y, x)
        self.panel = curses.panel.new_panel(self.win)
        self.panel.set_userptr(self)
        curses.panel.update_panels()
        self.colors = colors
        self.border = border
        self.hasscrollbar = hasscrollbar
        self._setdimensions(h, w, y, x)
        self.settitle(title)
        # list of additional border elements due to connections from other windows
        self.borderelements = []

    def _setdimensions(self, h, w, y, x):
        self.h = h
        self.w = w
        self.x = x
        self.y = y

        self.win.bkgdset(0, self.colors.background)

        # coordinates of upper left corner and width and height of inner part of window
        if self.h>=2:
            # we always have a title line
            self.iy = 1
            if self.hasleftborder():
                self.ix = 1
            else:
                self.ix = 0
            if self.hasrightborder() or self.hasscrollbar:
                self.iw = self.w - self.ix - 1
            else:
                self.iw = self.w - self.ix 

            if self.hasbottomborder():
                self.ih = h - self.iy - 1
            else:
                self.ih = h-self.iy
        else:
            # treat very small windows, which do not have a title line, separately
            self.ix = 0
            self.iy = 0
            self.ih = h
            self.iw = w

    # some error protected versions of the standard curses library

    def move(self, *args):
        self.win.move(*args)

    def addch(self, *args):
        try:
            self.win.addch(*args)
        except curses.error:
            pass

    def addstr(self, *args):
        try:
            self.win.addstr(*args)
        except curses.error:
            pass

    def addnstr(self, *args):
        try:
            self.win.addnstr(*args)
        except curses.error:
            pass

    def clrtoeol(self):
        self.win.clrtoeol()

    def clear(self):
        for y in range(self.ih):
            self.addstr(y+1, self.ix, " "*self.iw)

    def hline(self, x, y, c, n, attr):
        try:
            self.win.hline(x, y, c, n, attr)
        except TypeError:
            # workaround for Python 2.1.x
            for y in range(y, y+n):
                self.addch(x, y, c, attr)

    def vline(self, x, y, c, n, attr):
        try:
            self.win.vline(x, y, c, n, attr)
        except TypeError:
            # workaround for Python 2.1.x
            for x in range(x, x+n):
                self.addch(x, y, c, attr)

    def hastopborder(self):
        return self.border & config.BORDER_TOP

    def hasbottomborder(self):
        return self.border & config.BORDER_BOTTOM

    def hasleftborder(self):
        return self.border & config.BORDER_LEFT

    def hasrightborder(self):
        return self.border & config.BORDER_RIGHT

    def getborderends(self):
        """ return open ends of border as list of tuples (y, x, direction)
        where direction is one of "left", "right" , "up" or "down"
        """

        borderends = []
        if self.hastopborder() and not self.hasleftborder():
            borderends.append((self.y, self.x-1, "left"))
        if self.hastopborder() and not self.hasrightborder():
            borderends.append((self.y, self.x+self.w+1, "right"))

        if self.hasbottomborder() and not self.hasleftborder():
            borderends.append((self.y+self.h-1, self.x-1, "left"))
        if self.hasbottomborder() and not self.hasrightborder():
            borderends.append((self.y+self.h-1, self.x+self.w+1, "right"))

        if self.hasleftborder() and not self.hastopborder():
            borderends.append((self.y-1, self.x, "up"))
        if self.hasrightborder() and not self.hastopborder():
            borderends.append((self.y-1, self.x+self.w-1, "up"))

        if self.hasleftborder() and not self.hasbottomborder():
            borderends.append((self.y+self.h+1, self.x, "down"))
        if self.hasrightborder() and not self.hasbottomborder():
            borderends.append((self.y+self.h+1, self.x+self.w-1, "down"))

        return borderends

    def connectborderends(self, borderends):
        """ update list of border connections from other windows """
        self.borderelements = []
        for y, x, d in borderends:
            if self.win.enclose(y, x):
                if d == "right" and self.hasleftborder():
                    dy = y - self.y
                    if dy == 0 and self.hastopborder():
                        cel = curses.ACS_TTEE
                    elif dy == self.h-1 and self.hasbottomborder():
                        cel = curses.ACS_BTEE
                    else:
                        cel = curses.ACS_LTEE
                    self.borderelements.append((dy, 0, cel))
                elif d == "left" and self.hasrightborder():
                    dy = y - self.y
                    if dy == 0 and self.hastopborder():
                        cel = curses.ACS_TTEE
                    elif dy == self.h-1 and self.hasbottomborder():
                        cel = curses.ACS_BTEE
                    else:
                        cel = curses.ACS_LTEE
                    self.borderelements.append((dy, self.w-1, cel))
                elif d == "up" and self.hasbottomborder():
                    dx = x - self.x
                    if dx == 0 and self.hasleftborder():
                        cel = curses.ACS_LTEE
                    elif dx == self.w-1 and self.hasrightborder():
                        cel = curses.ACS_RTEE
                    else:
                        cel = curses.ACS_TTEE
                    self.borderelements.append((self.h, dx, cel))
                elif d == "down" and self.hastopborder():
                    dx = x - self.x
                    if dx == 0 and self.hasleftborder():
                        cel = curses.ACS_LTEE
                    elif dx == self.w-1 and self.hasrightborder():
                        cel = curses.ACS_RTEE
                    else:
                        cel = curses.ACS_BTEE
                    self.borderelements.append((0, dx, cel))

    def resize(self, h, w, y, x):
        """ resize window """
        try:
            self.win.resize(h, w)
            self.win.mvwin(y, x)
        except curses.error:
            pass
        self._setdimensions(h, w, y, x)

    def settitle(self, title):
        if title is not None:
            self.title = title
        else:
            self.title = None

    def scrollbardimensions(self, top, total):
        if total>0:
            totalheight = self.ih-4
            scrollbarbegin = 3 + totalheight*top/total
            scrollbarheight = totalheight*self.ih/total
            scrollbarheight = min(max(scrollbarheight, 1), totalheight-scrollbarbegin+3)

            return scrollbarbegin, scrollbarheight
        else:
            return 0, 0

    def drawscrollbar(self, top, total):
        if self.hasscrollbar:
            if not self.hasrightborder() and self.ih>2:
                self.vline(1, self.iw+self.ix, " ", self.ih, self.colors.background)
            if total>self.ih:
                xpos = self.iw+self.ix
                if top!=0:
                    self.addch(2, xpos, curses.ACS_UARROW, self.colors.scrollbararrow)
                if top+self.ih<total:
                    # self.addch(self.ih-1, xpos, curses.ACS_DARROW, self.colors.scrollbararrow)
                    self.addch(self.ih-1, xpos, "v", self.colors.scrollbararrow)
                scrollbarbegin, scrollbarheight = self.scrollbardimensions(top, total)
                self.vline(3, xpos, curses.ACS_CKBOARD, self.ih-4, self.colors.scrollbar)
                self.vline(scrollbarbegin, xpos, curses.ACS_CKBOARD, scrollbarheight, self.colors.scrollbarhigh)

    def bottom(self):
        """ bring window to bottom"""
        try:
            self.panel.bottom()
        except:
            pass
        else:
            log.debug("window '%s' bottom" % repr(self))
            hub.notify(events.focuschanged())

    def top(self):
        """ bring window to top"""
        try:
            self.panel.top()
            # The following call fixes the redrawing problem when switching between
            # the filelist and the playlist window reported by Dag Wieers.
            curses.panel.update_panels()
        except:
            pass
        else:
            log.debug("window '%s' top" % repr(self))
            hub.notify(events.focuschanged())

    def hide(self):
        """ hide window """
        try:
            self.panel.hide()
        except:
            pass
        else:
            log.debug("window '%s' hide" % repr(self))
            hub.notify(events.focuschanged())

    def hasfocus(self):
        """ is window on top and has thus the current focus? """
        return self.panel is curses.panel.top_panel()

    def enclose(self, y, x):
        "check whether y, x belongs to window (and not to other windows lying above)"

        # walk through panel stack
        p = curses.panel.top_panel()
        while p:
            if p is self.panel:
                return self.win.enclose(y, x)
            elif p.window().enclose(y, x):
                return 0
            p = p.below()
        return 0

    def stdscrtowin(self, y, x):
        begy, begx = self.win.getbegyx()
        return y-begy, x-begx

    def update(self):
        if self.title and self.h>=2:
            if self.hasfocus():
                topborder = 0
                # uncomment this to get the "thick" border of the old times
                # topborder = ord("=")
                attr = self.colors.activeborder
                try:
                    titleattr = self.colors.activetitle
                except AttributeError:
                    titleattr = self.colors.title
            else:
                topborder = 0
                attr = self.colors.border
                titleattr = self.colors.title

            # draw configured borders

            if self.hastopborder():
                self.hline(0, self.ix, curses.ACS_HLINE, self.iw, attr)
                # self.win.border(0, 0, topborder)
                t = encoding.encode(self.title)[:self.w-4]
                pos = (self.w-4-len(t))/2 
                self.addstr(0, pos, "[ %s ]" % t, titleattr)
                if self.hasleftborder():
                    self.addch(0, 0, curses.ACS_ULCORNER, attr)
                if self.hasrightborder():
                    self.addch(0, self.ix+self.iw, curses.ACS_URCORNER, attr)
                else:
                    self.addch(0, self.ix+self.iw, curses.ACS_HLINE, attr)
            else:
                t = self.title[:self.w]
                self.addstr(0, 0, t.center(self.w), titleattr)

            if self.hasbottomborder():
                self.hline(self.iy+self.ih, self.ix, curses.ACS_HLINE, self.iw, attr)
                if self.hasleftborder():
                    self.addch(self.iy+self.ih, 0, curses.ACS_LLCORNER, attr)
                if self.hasrightborder():
                    self.addch(self.iy+self.ih, self.ix+self.iw, curses.ACS_LRCORNER, attr)
                else:
                    self.addch(self.iy+self.ih, self.ix+self.iw, curses.ACS_HLINE, attr)

            if self.hasleftborder():
                if self.hastopborder():
                    self.vline(self.iy, 0, curses.ACS_VLINE, self.ih, attr)
                else:
                    self.vline(0, 0, curses.ACS_VLINE, self.ih+1, attr)

            if self.hasrightborder():
                if self.hastopborder():
                    self.vline(self.iy, self.ix+self.iw, curses.ACS_VLINE, self.ih, attr)
                else:
                    self.vline(0, self.ix+self.iw, curses.ACS_VLINE, self.ih+1, attr)

            # draw additional border elements
            for y, x, c in self.borderelements:
                self.addch(y, x, c, attr)

    # event handler

    def hidewindow(self, event):
        # subclasses of window explicitely have to subscribe to this event,
        # if they need to
        if event.window==self:
            self.hide()
