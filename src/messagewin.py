# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2004 Jörg Lehmann <joerg@luga.de>
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
import events, hub
import statusbar
import version
import window

# a scrollable window which supports automatic closing 

class messagewin(window.window):

    """ a scrollable window which supports automatic closing """

    def __init__(self, screen, maxh, maxw, channel, colors, title, items, autoclosetime):
        self.maxh = maxh
        self.maxw = maxw
        self.channel = channel
        self.autoclosetime = autoclosetime
        self.items = items
        self.first = 0

        # for identification purposes, we only generate this once
        self.hidewindowevent = events.hidewindow(self)
        
        self.keybindings = config.keybindings.filelistwindow

        window.window.__init__(self, screen, 1, 1, 0, 0, colors, title)

        self.channel.subscribe(events.keypressed, self.keypressed)
        self.channel.subscribe(events.mouseevent, self.mouseevent)
        self.channel.subscribe(events.hidewindow, self.hidewindow)
        self.channel.subscribe(events.focuschanged, self.focuschanged)

    def _outputlen(self, width):
        """number of lines in window"""
        return len(self.items)

    def _resize(self):
        if self.maxw<=80:
            width = self.maxw
        else:
            width = 80 + int((self.maxw-80)*0.8)
        height = min(self._outputlen(width-2)+2, self.maxh-3)
        y = max(0, (self.maxh-height)/2)
        x = max(0, (self.maxw-width)/2)
        window.window.resize(self, height, width, y, x)

    def resize(self, maxh, maxw):
        self.maxh = maxh
        self.maxw = maxw
        self._resize()
        if self.hasfocus():
            self.update()

    def show(self):
        self._resize()
        self.first = 0
        self.top()
        self.update()
        if self.autoclosetime:
            hub.notify(events.sendeventin(self.hidewindowevent,
                                              self.autoclosetime,
                                              replace=1))

    def showitems(self):
        """ has to be implemented by derivec classes """
        pass
    
    # event handler

    def keypressed(self, event):
        if self.hasfocus():
            key = event.key
            # XXX: do we need own keybindings for help?
            if key in self.keybindings["selectnext"]:
                self.first = min(self._outputlen(self.iw)-self.ih, self.first+1)
            elif key in self.keybindings["selectprev"]:
                self.first = max(0, self.first-1)
            elif key in self.keybindings["selectnextpage"]:
                self.first = min(self._outputlen(self.iw)-self.ih, self.first+self.ih)
            elif key in self.keybindings["selectprevpage"]:
                self.first = max(0, self.first-self.iw)
            elif key in self.keybindings["selectfirst"]:
                self.first = 0
            elif key in self.keybindings["selectlast"]:
                self.first = self._outputlen(self.iw)-self.ih
            else:
                self.hide()
                raise hub.TerminateEventProcessing
                return

            self.update()
            if self.autoclosetime:
                hub.notify(events.sendeventin(self.hidewindowevent,
                                                  self.autoclosetime,
                                                  replace=1))
        
            raise hub.TerminateEventProcessing

    def mouseevent(self, event):
        if self.hasfocus():
            self.hide()
            raise hub.TerminateEventProcessing

    def focuschanged(self, event):
        if self.hasfocus():
            sbar = [("PyTone %s" % version.version, config.colors.statusbar.key)]
            sbar += statusbar.separator
            sbar += [(version.copyright, config.colors.statusbar.description)]
            sbar += statusbar.terminate
            hub.notify(events.statusbar_update(0, sbar))

    def update(self):
        window.window.update(self)
        self.showitems()



