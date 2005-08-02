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

##############################################################################
# descriptions for functions and keys
#
# descriptions: dictionary with entries
#  "general":  global function descriptions
#  "filelist": filelist function descriptions
#  "playlist": playlistlist function descriptions
# which map from
#   name of function to 
#   2-tuple of very short (for statusbar) and short description of
#   corresponding function
#
# keyname:  dictionary which maps from  keycodes to the names of the keys
##############################################################################

descriptions = {
    "general": {
          "refresh":           (_("refresh"), _("refresh display")),
          "exit":              (_("exit"), _("exit PyTone (press twice)")), 
          "playerstart":       (_("play"), _("start main player")),
          "playerpause":       (_("pause"), _("pause main player")),
          "playernextsong":    (_("next song"), _("advance to next song")),
          "playerprevioussong":(_("previous song"), _("go back to previous song")),
          "playerrewind":      (_("rewind"), _("rewind main player")),
          "playerforward":     (_("forward"), _("forward main player")),
          "playerstop":        (_("stop"), _("stop main player")),
          "playlistdeleteplayedsongs":
                               (_("delete played"), _("delete played songs from playlist")),
          "playlistreplay":    (_("replay songs"), _("mark all songs in playlist as unplayed")),
          "playlisttoggleautoplaymode":
                               (_("toggle playlist mode"), _("toggle the playlist mode")),
          "playlistclear":     (_("clear"), _("clear playlist")),
          "playlistsave":      (_("save"), _("save playlist")),
          "playlistload":      (_("load"), _("load playlist")),
          "showhelp":          (_("help"), _("show help")),
          "showlog":           (_("log"), _("show log messages")),
          "showstats":         (_("statistics"), _("show statistical information about database(s)")),
          "showiteminfolong":  (_("item info"), _("show information about selected item")),
          "toggleiteminfowindow":  (_("toggle item info"), _("toggle information shown in item info window")),
          "togglelayout":      (_("toggle layout"), _("toggle layout")),
          "volumeup":          (_("volume up"), _("increase output volume")),
          "volumedown":        (_("volume down"), _("decrease output volume")),
    },
    "filelistwindow": {
          "selectnext":        (_("down"), _("move to the next entry")),
          "selectprev":        (_("up"), _("move to the previous entry")),
          "selectnextpage":    (_("page down"), _("move to the next page")),
          "selectprevpage":    (_("page up"), _("move to previous page")),
          "selectfirst":       (_("first"), _("move to the first entry")),
          "selectlast":        (_("last"), _("move to the last entry")),
          "dirdown":           (_("enter dir"), _("enter selected directory")),
          "dirup":             (_("exit dir"), _("go directory up")),
          "addsongtoplaylist": (_("add song"), _("add song to playlist")),
          "adddirtoplaylist":  (_("add dir"), _("add directory recursively to playlist")),
          "playselectedsong":  (_("immediate play"), _("play selected song immediately")),
          "activateplaylist":  (_("switch to playlist"), _("switch to playlist window")),
#          "generaterandomlist":(_("random suggestion"), _("generate random song list")),
          "insertrandomlist":  (_("random add dir"), _("add random contents of dir to playlist")),
          "search":            (_("search"), _("search entry")),
          "repeatsearch":      (_("repeat search"), _("repeat last search")),
          "rescan":            (_("rescan"), _("rescan/update id3 info for selection")),
          },
    "playlistwindow": {
          "selectnext":        (_("down"), _("move to the next entry")),
          "selectprev":        (_("up"), _("move to the previous entry")),
          "selectnextpage":    (_("page down"), _("move to the next page")),
          "selectprevpage":    (_("page up"), _("move to previous page")),
          "selectfirst":       (_("first"), _("move to the first entry")),
          "selectlast":        (_("last"), _("move to the last entry")),
          "moveitemup":        (_("move song up"), _("move song up")),  
          "moveitemdown":      (_("move song down"), _("move song down")),
          "shuffle":           (_("shuffle"), _("shuffle playlist")),
          "deleteitem":        (_("delete"), _("delete entry")),
          "playselectedsong":  (_("immediate play"), _("play selected song immediately")),
          "activatefilelist":  (_("switch to database"), _("switch to database window")),
          "rescan":            (_("rescan"), _("rescan/update id3 info for selection")),
          "filelistjumptoselectedsong":
                               (_("jump to selected"), _("jump to selected song in filelist window")),
          }
    }

# prefill keynames 
keynames = {}
for c in range(32):
    keynames[c] = _("CTRL")+"-"+chr(c+64)
for c in range(33, 128):
    keynames[c] = chr(c)


# special keys (incomplete, but sufficient list)
keynames[ord("\t")]            = _("<TAB>")
keynames[ord("\n")]            = _("<Return>")
keynames[27]                   = _("<ESC>")
keynames[32]                   = _("<Space>")
keynames[curses.KEY_BACKSPACE] = _("<Backspace>")
keynames[curses.KEY_DC]        = _("<Del>")
keynames[curses.KEY_DOWN]      = _("<Down>")
keynames[curses.KEY_END]       = _("<End>")
keynames[curses.KEY_ENTER]     = _("<Enter>")
keynames[curses.KEY_HOME]      = _("<Home>")
keynames[curses.KEY_IC]        = _("<Insert>")
keynames[curses.KEY_LEFT]      = _("<Left>")
keynames[curses.KEY_NPAGE]     = _("<PageDown>")
keynames[curses.KEY_PPAGE]     = _("<PageUp>")
keynames[curses.KEY_RIGHT]     = _("<Right>")
keynames[curses.KEY_UP]        = _("<Up>")

# function keys
for nr in range(1, 13):
    keynames[eval("curses.KEY_F%d" % nr)] = "<F%d>" %nr


# alt+key
for key in keynames.keys():
    keynames[key+1024] = _("ALT")+"-"+keynames[key]


