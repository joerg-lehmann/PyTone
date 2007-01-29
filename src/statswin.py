# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2005 Jörg Lehmann <joerg@luga.de>
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
import messagewin
import hub, requests

class statswin(messagewin.messagewin):

    def __init__(self, screen, maxh, maxw, channel, numberofsongdbs):
        # column number of message string
        messagewin.messagewin.__init__(self, screen, maxh, maxw, channel,
                                       config.colors.statswindow,
                                       _("PyTone Statistics"), [],
                                       config.statswindow.autoclosetime)
        self.numberofsongdbs = numberofsongdbs

    def _outputlen(self, iw):
        """number of lines in window with inner widht iw"""
        result = self.numberofsongdbs*4 + 3
        return result

    def showitems(self):
        lines = []
        stats = hub.request(requests.getsongdbmanagerstats())
        indent = " "*3
        for songdbstats in stats.songdbsstats:
            dbidstring = _("Database %s") % songdbstats.id + ":"
            dbstatstring = _("%d songs, %d albums, %d artists, %d tags") % (songdbstats.numberofsongs,
									    songdbstats.numberofalbums,
									    songdbstats.numberofartists,
									    songdbstats.numberoftags)

            lines.append((dbidstring, dbstatstring))
            if songdbstats.type == "local":
                dbtypestring = _("local database (db file: %s)") % (songdbstats.dbfile)
            else:
                dbtypestring = _("remote database (server: %s)") % (songdbstats.location)
            lines.append((indent + _("type") + ":", dbtypestring))
            lines.append((indent + _("base directory") + ":", songdbstats.basedir)) 
            dbcachesizestring =  "%dkB" % songdbstats.cachesize
            lines.append((indent + _("cache size") + ":", dbcachesizestring))

        lines.append(("", ""))
        cachestatsstring = _("%d requests, %d / %d objects") % (stats.requestcacherequests, stats.requestcachesize,
                                                                stats.requestcachemaxsize)
        if stats.requestcachemaxsize != 0:
            cachestatsstring = cachestatsstring + " (%d%%)" % (100*stats.requestcachesize//stats.requestcachemaxsize)
        lines.append((_("Request cache size") + ":", cachestatsstring))
        totalrequests = stats.requestcachehits + stats.requestcachemisses
        if totalrequests != 0:
            percentstring = " (%d%%)" % (100*stats.requestcachehits//totalrequests)
        else:
            percentstring = ""
        lines.append((_("Request cache stats") + ":",
                      (_("%d hits / %d requests") % (stats.requestcachehits, totalrequests)) + percentstring))

        wc1 = max([len(lc) for lc, rc in lines]) + 1
        if wc1 > 0.6*self.iw:
            wc1 = int(0.6*self.iw)
        wc2 = self.iw - wc1
        y = self.iy
        for lc, rc in lines:
            self.move(y, self.ix)
            self.addstr(lc.ljust(wc1)[:wc1], self.colors.description)
            self.addstr(rc.ljust(wc2)[:wc2], self.colors.content)
            y += 1
