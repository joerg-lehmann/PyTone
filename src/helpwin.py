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

import config
import help
import events, hub
import messagewin
import statusbar

def getitems(section):
    items = []
    if section:
        for function in config.keybindings[section].asdict().keys():
            keys = list(config.keybindings[section][function])
            keys.sort()
            keynames = []
            for key in keys:
                keynames += [help.keynames[key]]
            descr = help.descriptions[section][function][1]
            items += [(keynames, descr)]

    return items


class helpwin(messagewin.messagewin):

    def __init__(self, screen, maxh, maxw, channel):
        messagewin.messagewin.__init__(self, screen, maxh, maxw, channel,
                                       config.colors.helpwindow,
                                       _("PyTone Help"), [],
                                       config.helpwindow.autoclosetime)

        sbar = statusbar.generatedescription("general", "showhelp")
        hub.notify(events.updatestatusbar(2, sbar))

    def showitems(self):
        y = self.iy
        for item in self.items[self.first:]:
            self.addstr(y, 1, " "*self.iw, self.colors.background)
            self.move(y, 1)
            for keyname in item[0][:-1]:
                self.addstr(keyname, self.colors.key)
                self.addstr("/", self.colors.description)
            self.addstr(item[0][-1], self.colors.key)
            assert type(item[1])==type(""), item[1]
            self.addnstr(y, 35, item[1], self.iw-35)
            y += 1
            if y>=self.iy+self.ih:
                break

    def showhelp(self, context):
        self.items = getitems("general")+getitems(context)
        self.items.sort()
        self.show()
