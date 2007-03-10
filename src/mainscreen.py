# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004, 2005 Jörg Lehmann <joerg@luga.de>
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

# uncomment next line for pychecker
# import gettext; gettext.install("PyTone", "")

import curses, curses.panel, fcntl, os, struct, termios
import events, hub
import filelistwin
import playlistwin
import playerwin
import iteminfowin
import lyricswin
import helpwin
import inputwin
import mixerwin
import log
import logwin
import statswin
import statusbar
import config


class mainscreen:
    def __init__(self, screen, songdbids, playerids, plugins):
        self.screen = screen
        self.layout = config.general.layout
        self.h, self.w = self.getmaxyx()
        log.debug("h=%d, w=%d" % (self.h, self.w))
        self.channel = hub.newchannel()
        self.keybindings = config.keybindings.general
        self.done = False

        self.statusbar = statusbar.statusbar(screen, self.h-1, self.w, self.channel)

        # first we setup the input window in order to have it as first window
        # in the keypressed events lists.
        if config.inputwindow.type=="popup":
            self.inputwin = inputwin.popupinputwin(screen, self.h, self.w, self.channel)
        else:
            self.inputwin = inputwin.statusbarinputwin(screen, self.h, self.w, self.channel)

        # setup the four main windows
        windowslayout = self.calclayout()
        self.playerwin = playerwin.playerwin(screen, windowslayout["playerwin"], self.channel, playerids[0])
        self.iteminfowin = iteminfowin.iteminfowin(screen, windowslayout["iteminfowin"], self.channel, playerids, playerids[1])
        self.filelistwin = filelistwin.filelistwin(screen, windowslayout["filelistwin"], self.channel, songdbids)
        self.playlistwin = playlistwin.playlistwin(screen, windowslayout["playlistwin"], self.channel, "main")
        self.connectborders()

        # setup additional windows which appear on demand
        self.helpwin = helpwin.helpwin(screen, self.h, self.w, self.channel)

        self.logwin = logwin.logwin(screen, self.h, self.w, self.channel)
        self.statswin = statswin.statswin(screen, self.h, self.w, self.channel, len(songdbids))

        self.iteminfowinlong = iteminfowin.iteminfowinlong(screen, self.h, self.w, self.channel)
        self.lyricswin = lyricswin.lyricswin(screen, self.h, self.w, self.channel)

        self.mixerwin = None
        if config.mixer.device:
            try:
                if config.mixerwindow.type=="popup":
                    self.mixerwin = mixerwin.popupmixerwin(screen, self.h, self.w, self.channel)
                else:
                    self.mixerwin = mixerwin.statusbarmixerwin(screen, self.h, self.w, self.channel)

            except IOError, e:
                log.warning('error "%s" during mixer init - disabling mixer' % e)
        else:
            # disbable keybindings to obtain correct help window contents
            del config.keybindings.general.volumeup
            del config.keybindings.general.volumedown

        # now we start the plugins
        for pluginmodule, pluginconfig in plugins:
            plugin_class = pluginmodule.plugin
            if plugin_class:
                plugin = plugin_class(self.channel, pluginconfig, self)
                plugin.start()

        self.channel.subscribe(events.keypressed, self.keypressed)
        self.channel.subscribe(events.activateplaylist, self.activateplaylist)
        self.channel.subscribe(events.activatefilelist, self.activatefilelist)
        self.channel.subscribe(events.quit, self.quit)

        hub.notify(events.activatefilelist())

    def run(self):
        """ main loop of control thread """
        skipcount = 0
        while not self.done:
            try:
                key = self.screen.getch()

                if key==27:
                    # handle escape sequence (e.g. alt+key)
                    key = self.screen.getch()+1024

                if key==curses.KEY_MOUSE:
                    mouse = curses.getmouse()
                    x, y = mouse[1:3]
                    state = mouse[4]
                    hub.notify(events.mouseevent(y, x, state))
                elif key==curses.KEY_RESIZE:
                    self.resizeterminal()
                elif key in self.keybindings["exit"]:
                    curses.halfdelay(5)
                    key = self.screen.getch()
                    curses.halfdelay(1)
                    if key in self.keybindings["exit"]:
                        break
                elif key!=-1:
                    hub.notify(events.keypressed(key), 50)

                self.channel.process()

                # update screen
                if key == -1 or skipcount >= config.general.throttleoutput:
                    curses.panel.update_panels()
                    curses.doupdate()
                    skipcount = 0
                else:
                    skipcount += 1

            except KeyboardInterrupt:
                pass

    def quit(self, event):
        """ cleanup """
        self.done = True

    def getmaxyx(self):
        # taken from http://dag.wieers.com/home-made/dstat/
        try:
            h, w = int(os.environ["LINES"]), int(os.environ["COLUMNS"])
        except KeyError:
            try:
                h, w = curses.tigetnum('lines'), curses.tigetnum('cols')
            except:
                try:
                    s = struct.pack('HHHH', 0, 0, 0, 0)
                    x = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, s)
                    h, w = struct.unpack('HHHH', x)[:2]
                except:
                    h, w = 25, 80

        # take into account minimal height and width according to layout
        if self.layout == "onecolumn":
            minh = 27
            minw = 25
        else:
            minh = 17
            minw = 65
        return max(h, minh), max(w, minw)

    def calclayout(self):
        """ calculate layout of four main windows for given height h and width w of mainscreen and
        layout type layout"""
        result = {}
        if self.layout == "twocolumn":
            leftpanelw = int(self.w/2.2)
            rightpanelw = self.w-leftpanelw
            rightpanelx = leftpanelw

            if config.playerwindow.border == config.BORDER_COMPACT:
                playerwinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_RIGHT
            elif config.playerwindow.border == config.BORDER_ULTRACOMPACT:
                playerwinb = config.BORDER_LEFT | config.BORDER_TOP
            else:
                playerwinb = config.playerwindow.border
            if playerwinb & config.BORDER_BOTTOM:
                playerwinh = 3
            else:
                playerwinh = 2
            result["playerwin"] = playerwinh, rightpanelw, 0, rightpanelx, playerwinb

            if config.iteminfowindow.border == config.BORDER_COMPACT:
                iteminfowinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_RIGHT
            elif config.iteminfowindow.border == config.BORDER_ULTRACOMPACT:
                iteminfowinb = config.BORDER_LEFT | config.BORDER_TOP
            else:
                iteminfowinb = config.iteminfowindow.border
            if iteminfowinb & config.BORDER_BOTTOM:
                iteminfowinh = 6
            else:
                iteminfowinh = 5
            result["iteminfowin"] = iteminfowinh, rightpanelw, playerwinh, rightpanelx, iteminfowinb

            if config.filelistwindow.border == config.BORDER_COMPACT:
                filelistwinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_BOTTOM
            elif config.filelistwindow.border == config.BORDER_ULTRACOMPACT:
                filelistwinb = config.BORDER_TOP
            else:
                filelistwinb = config.filelistwindow.border
            result["filelistwin"] = self.h-1, leftpanelw, 0, 0, filelistwinb
            
            if config.playlistwindow.border == config.BORDER_COMPACT:
                playlistwinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_RIGHT | config.BORDER_BOTTOM
            elif config.playlistwindow.border == config.BORDER_ULTRACOMPACT:
                playlistwinb = config.BORDER_LEFT | config.BORDER_TOP
            else:
                playlistwinb = config.playlistwindow.border
            result["playlistwin"] = (self.h-iteminfowinh-playerwinh-1, rightpanelw, iteminfowinh+playerwinh, rightpanelx,
                                     playlistwinb)

        else:
            # onecolumn layout
            if config.playerwindow.border == config.BORDER_COMPACT:
                playerwinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_RIGHT
            elif config.playerwindow.border == config.BORDER_ULTRACOMPACT:
                playerwinb = config.BORDER_TOP
            else:
                playerwinb = config.playerwindow.border
            if playerwinb & config.BORDER_BOTTOM:
                playerwinh = 3
            else:
                playerwinh = 2
            result["playerwin"] = playerwinh, self.w, 0, 0, playerwinb

            if config.iteminfowindow.border == config.BORDER_COMPACT:
                iteminfowinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_RIGHT
            elif config.iteminfowindow.border == config.BORDER_ULTRACOMPACT:
                iteminfowinb = config.BORDER_TOP
            else:
                iteminfowinb = config.iteminfowindow.border
            if iteminfowinb & config.BORDER_BOTTOM:
                iteminfowinh = 6
            else:
                iteminfowinh = 5
            result["iteminfowin"] = iteminfowinh, self.w, playerwinh, 0, iteminfowinb

            if config.filelistwindow.border == config.BORDER_COMPACT:
                filelistwinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_RIGHT
            elif config.filelistwindow.border == config.BORDER_ULTRACOMPACT:
                filelistwinb = config.BORDER_TOP
            else:
                filelistwinb = config.filelistwindow.border
            filelistwinh = int(self.h/2)
            result["filelistwin"] = filelistwinh, self.w, playerwinh+iteminfowinh, 0, filelistwinb

            if config.playlistwindow.border == config.BORDER_COMPACT:
                playlistwinb = config.BORDER_LEFT | config.BORDER_TOP | config.BORDER_RIGHT | config.BORDER_BOTTOM
            elif config.playlistwindow.border == config.BORDER_ULTRACOMPACT:
                playlistwinb = config.BORDER_TOP
            else:
                playlistwinb = config.playlistwindow.border
            result["playlistwin"] = (self.h-iteminfowinh-playerwinh-filelistwinh-1, self.w, playerwinh+iteminfowinh+filelistwinh, 0,
                                     playlistwinb)

        return result

    def connectborders(self):
        borderends = []
        mainwindows = [self.filelistwin, self.playerwin, self.iteminfowin, self.playlistwin]
        for win in mainwindows:
            borderends.extend(win.getborderends())

        for win in mainwindows:
            win.connectborderends(borderends)
            win.update()

    def refresh(self):
        # refresh screen (i don't know any better way...)
        self.screen.clear()
        self.filelistwin.update()
        self.playlistwin.update()
        self.playerwin.update()
        self.iteminfowin.update()
        self.statusbar.update()

    def resizeterminal(self):
        self.h, self.w = self.getmaxyx()

        windows = self.calclayout()
        self.filelistwin.resize(windows["filelistwin"])
        self.playerwin.resize(windows["playerwin"])
        self.iteminfowin.resize(windows["iteminfowin"])
        self.playlistwin.resize(windows["playlistwin"])
            
        self.statusbar.resize(self.h-1, self.w)
        self.helpwin.resize(self.h, self.w)
        self.logwin.resize(self.h, self.w)
        self.statswin.resize(self.h, self.w)
        self.inputwin.resize(self.h, self.w)

        if self.mixerwin:
            self.mixerwin.resize(self.h, self.w)

        self.connectborders()

        self.filelistwin.update()
        self.playlistwin.update()
        self.playerwin.update()
        self.iteminfowin.update()
        self.statusbar.update()

    # event handler

    def keypressed(self, event):
        key = event.key
        if key in self.keybindings["refresh"]:
            self.refresh()
        elif key in self.keybindings["playlistdeleteplayedsongs"]:
            hub.notify(events.playlistdeleteplayedsongs())
        elif key in self.keybindings["playlistclear"]:
            hub.notify(events.playlistclear())
            hub.notify(events.activatefilelist())
        elif key in self.keybindings["playlistreplay"]:
            hub.notify(events.playlistreplay())
        elif key in self.keybindings["playlistsave"]:
            hub.notify(events.playlistsave())
        elif key in self.keybindings["playlisttoggleautoplaymode"]:
            hub.notify(events.playlisttoggleautoplaymode())
        elif key in self.keybindings["showhelp"]:
            if self.filelistwin.hasfocus():
                context = "filelistwindow"
            elif self.playlistwin.hasfocus():
                context = "playlistwindow"
            else:
                context = None
            self.helpwin.showhelp(context)
        elif key in self.keybindings["showlog"]:
            self.logwin.show()
        elif key in self.keybindings["showstats"]:
            self.statswin.show()
        elif key in self.keybindings["showiteminfolong"]:
            self.iteminfowinlong.show()
        elif key in self.keybindings["showlyrics"]:
            # XXX disabled at the moment
            return 
            self.lyricswin.show()
        elif key in self.keybindings["togglelayout"]:
            self.layout = self.layout == "onecolumn" and "twocolumn" or "onecolumn"
            self.resizeterminal()
        else:
            log.debug("unknown key: %d" % key)

    def activateplaylist(self, event):
        self.playlistwin.top()

    def activatefilelist(self, event):
        self.filelistwin.top()
