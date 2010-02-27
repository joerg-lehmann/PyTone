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

import config
import curses
import string
import events, hub
import statusbar
import window

# string.printable is not updated when locale is changed (this is a known bug, which
# however is not planed to be fixed), so we just do this by ourselves

printable = string.digits + string.letters + string.punctuation + string.whitespace

class inputwin(window.window):

    """ generic input window """

    def __init__(self, screen, maxh, maxw, channel):
        self.channel = channel
        self.keybindings = config.keybindings.general
        self.inputstring = ""
        self.inputprompt = ""

        self.hide()

        self.channel.subscribe(events.keypressed, self.keypressed)
        self.channel.subscribe(events.mouseevent, self.mouseevent)
        self.channel.subscribe(events.requestinput, self.requestinput)
        self.channel.subscribe(events.focuschanged, self.focuschanged)

    # we also need a blinking cursor, whenever we have the focus

    def hide(self):
        try:
            curses.curs_set(0)
        except:
            pass
        window.window.hide(self)

    def top(self):
        try:
            curses.curs_set(1)
        except:
            pass
        window.window.top(self)
        
    # event handler

    def keypressed(self, event):
        if self.hasfocus():
            key = event.key
            if 32 <= key <= 255 and chr(key) in printable:
                if len(self.inputstring)+len(self.inputprompt)<self.iw-1:
                    self.inputstring += chr(key)
                else:
                    self.inputstring = self.inputstring[:-1]+chr(key)
            elif key == ord("\n"):
                self.hide()
            elif key == 1023:
                self.hide()
            elif key == curses.KEY_BACKSPACE:
                self.inputstring = self.inputstring[:-1]
                
            self.update()
            self.inputhandler(self.inputstring, key)
            raise hub.TerminateEventProcessing

    def mouseevent(self, event):
        if self.hasfocus():
            self.hide()
            raise hub.TerminateEventProcessing

    def focuschanged(self, event):
        # we either have focus, or we disappear...
        pass
        #if not self.hasfocus():
        #    self.hide()

    def requestinput(self, event):
        self.inputstring = ""
        self.inputprompt = event.prompt
        self.inputhandler = event.handler
        self.title = event.title
        self.top()
        self.update()

    # window update method
        
    def update(self):
        window.window.update(self)
        
        self.addstr(self.iy, self.ix, " "*(self.iw-1))
        self.move(self.iy, self.ix)
        self.addstr(self.inputprompt, self.colors.description)
        self.addstr(self.inputstring, self.colors.content)


class popupinputwin(inputwin):

    """ input window which appears as a popup at the center of the screen """
    
    def __init__(self, screen, maxh, maxw, channel):
        # calculate size and position 
        h = 3
        w = 40
        y = (maxh-h)/2
        x = (maxw-w)/2

        window.window.__init__(self,
                               screen, h, w, y, x,
                               config.colors.inputwindow,
                               "Input")

        inputwin.__init__(self, screen, maxh, maxw, channel)

    def resize(self, maxh, maxw):
        h = 3
        w = 40
        y = (maxh-h)/2
        x = (maxw-w)/2
        window.window.resize(self, h, w, y, x)

    def requestinput(self, event):
        inputwin.requestinput(self, event)
        if self.inputprompt:
            self.inputprompt = self.inputprompt + " "
            
        sbar = []
        sbar += [("Enter", config.colors.statusbar.key),
                 (": "+_("ok"), config.colors.statusbar.description)]
        sbar += statusbar.separator
        sbar += [("ESC", config.colors.statusbar.key),
                 (": "+_("cancel"), config.colors.statusbar.description)]
        sbar += statusbar.terminate
        hub.notify(events.statusbar_update(0, sbar))

        self.update()


class statusbarinputwin(inputwin):

    """ input window which appears in the statusbar """

    def __init__(self, screen, maxh, maxw, channel):
        # calculate size and position 

        window.window.__init__(self,
                               screen, 1, maxw-1, maxh-1, 0,
                               config.colors.inputwindow)

        inputwin.__init__(self, screen, maxh, maxw, channel)

    def resize(self, maxh, maxw):
        window.window.resize(self, 1, maxw, maxh-1, 0)

    def requestinput(self, event):
        inputwin.requestinput(self, event)
        self.inputprompt = self.title + ": "
        self.update()
