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
import log
import messagewin
import time

class logwin(messagewin.messagewin):

    def __init__(self, screen, maxh, maxw, channel):
        # column number of message string
        self.mc = 12
        messagewin.messagewin.__init__(self, screen, maxh, maxw, channel,
                                       config.colors.logwindow,
                                       _("PyTone Messages"),
                                       log.items,
                                       config.logwindow.autoclosetime)

    def _outputlen(self, iw):
        """number of lines in window with inner widht iw"""
        result = 0
        for item in self.items:
            result += len(item[2])/(iw-self.mc+2)+1
        return result

    def showitems(self):
        y = self.iy
        for item in log.items[self.first:]:
            self.addstr(y, 1, " "*self.iw, self.colors.background)
            self.addstr(y, 1, log._desc[item[0]][0].upper(), self.colors.time)
            self.addstr(y, 3, time.strftime("%H:%M:%S", time.localtime(item[1])), self.colors.time)

            if item[0] == log._DEBUG:
                color = self.colors.debug
            elif item[0] == log._INFO:
                color = self.colors.info
            elif item[0] == log._WARNING:
                color = self.colors.warning
            else:
                color = self.colors.error
            # width of message column
            mw = self.iw-self.mc+1
            if len(item[2])<=mw:
                self.addstr(y, self.mc, item[2], color)
            else:
                words = item[2].split()
                s = words.pop(0)
                while words and len(s)+len(words[0])<mw:
                    s += " %s" % words.pop(0)
                self.addstr(y, self.mc, s, color)
                y += 1
                if y>=self.iy+self.ih:
                    break
                self.addstr(y, 1, " "*self.iw, self.colors.background)
                s=" ".join(words)
                self.addnstr(y, self.mc, s, mw, color)

            y += 1
            if y>=self.iy+self.ih:
                break
