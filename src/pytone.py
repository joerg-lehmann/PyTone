#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004, 2005, 2007 Jörg Lehmann <joerg@luga.de>
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

import curses, os, os.path, signal, imp, sys

##############################################################################
# gettext initialization.
##############################################################################

# We have to initialize gettext very early, before importing our
# modules. Assume that the locales lie in same dir as this
# module. This may not be the case, if the .mo files are installed at
# their proper location.

try:
    import gettext
    locallocaledir = os.path.join(os.path.dirname(sys.argv[0]), "../locale")
    gettext.install("PyTone", locallocaledir, unicode=True)
except:
    # Disable localization if there is any problem with the above.
    # This works around a problem with Python 2.1
    import __builtin__
    __builtin__.__dict__['_'] = lambda s: s

##############################################################################
# locale initialization
##############################################################################

import locale
locale.setlocale(locale.LC_ALL, '')

##############################################################################
# create .pytone dir in user home
##############################################################################
try:
    os.mkdir(os.path.expanduser("~/.pytone"))
except OSError, e:
    if e.errno!=17:
        raise

##############################################################################
# process commandline options and read config file
##############################################################################

import config
# process the command line first, because a different location for the
# config file may be given there
config.processcommandline()
config.processconfig()

# now that the configuration has been read, we can imort the log
# module and initialize the debug file if necessary
import log
log.initdebugfile(config.general.debugfile)

# log version (but do this after the debug file has been initialized,
# such that the version gets included there)
import version
log.info(_("PyTone %s startup") % version.version)

import errors
import mainscreen
import helper
import hub, events
import services.songdb
import services.player
import services.timer

# Uncomment the next line, if you want to experiment a little bit with
# the number of bytecode instructions after which a context switch
# occurs.

# sys.setcheckinterval(250)


##############################################################################
# start various services
##############################################################################

# catch any exceptions during service startup to be able to shut down
# all already running services when something goes wrong
try:
    # timer service. We start this first so that other services can register
    # there periodic events with this service
    services.timer.timer().start()

    # Determine plugins specified in the config file and read their config.
    # The result goees into a list of tuples (pluginmodule, pluginconfig).
    plugins = []

    userpluginpath = os.path.expanduser("~/.pytone/plugins/")
    cwd = os.path.abspath(os.path.dirname(sys.argv[0]))
    globalpluginpath = os.path.join(cwd, "plugins")
    pluginpath = [userpluginpath, globalpluginpath]

    for name in config.general.plugins:
        try:
            # We use imp.find_module to narrow down the plugin search path
            # to the two possible locations. Setting sys.path correspondingly
            # would not work, however, since then the plugin could not
            # import its needed modules. 
            fp, pathname, description = imp.find_module(name, pluginpath)
            pluginmodule = imp.load_module(name, fp, pathname, description)
            # 
            # process configuration of plugin
            pluginconfig = pluginmodule.config
            if pluginconfig is not None:
                config.readconfigsection("plugin.%s" % name, pluginconfig)
                config.finishconfigsection(pluginconfig)
                pluginconfig = pluginconfig()
            plugins.append((pluginmodule, pluginconfig))
        except Exception, e:
             log.error(_("Cannot load plugin '%s': %s") % (name, e))
             log.debug_traceback()

    # initialize song database manager and start it immediately so
    # that it can propagate quit events in case something goes wrong
    # when setting up the databases
    songdbmanager = services.songdb.songdbmanager()
    songdbmanager.start()

    # song databases
    songdbids = []
    for songdbname in config.database.getsubsections():
        try:
            songdbid = songdbmanager.addsongdb(songdbname, config.database[songdbname])
            if songdbid:
                songdbids.append(songdbid)
        except Exception, e:
            log.error("cannot initialize db %s: %s" % (id, e))

    if not songdbids:
        # raise last configuration error
        raise 

    # network service
    if config.network.enableserver:
        import network
        network.tcpserver(config.network.bind, config.network.port).start()
    if config.network.socketfile:
        import network
        network.unixserver(os.path.expanduser(config.network.socketfile)).start()

    # Now that the basic services have been started, we can initialize
    # the players. This has to be done last because the players
    # immediately start requesting a new song
    playerids = [services.player.initplayer("main", config.player.main),
                 services.player.initplayer("secondary", config.player.secondary)]

except:
    # if something goes wrong, shutdown all already running services
    hub.notify(events.quit(), 100)
    raise

##############################################################################
# basic curses library setup...
##############################################################################

def cursessetup():
    # Initialize curses library
    stdscr = curses.initscr()

    # Turn off echoing of keys
    curses.noecho()

    # In keypad mode, escape sequences for special keys
    # (like the cursor keys) will be interpreted and
    # a special value like curses.KEY_LEFT will be returned
    stdscr.keypad(1)

    # allow 8-bit characters to be input
    curses.meta(1)

    # enter raw mode, thus disabling interrupt, quit, suspend and flow-control keys
    curses.raw()

    # wait at maximum for 1/10th of seconds for keys pressed by user
    curses.halfdelay(1)

    if config.general.colorsupport == "auto":
        # Try to enable color support
        try:
            curses.start_color()
        except:
            log.warning("terminal does not support colors: disabling color support")

        # now check whether color support really has been enabled
        if curses.has_colors():
            config.configcolor._colorenabled = 1
    elif config.general.colorsupport == "on":
        curses.start_color()
        config.configcolor._colorenabled = 1

    # Check for transparency support of terminal
    # use_default_colors(), which will be integrated in python 2.4.
    # Before that happens we try to use our own cursext c-extension
    try:
        curses.use_default_colors()
        config.configcolor._colors["default"] = -1
    except:
        try:
            import cursext
            if cursext.useDefaultColors():
                config.configcolor._colors["default"] = -1
            else:
                log.warning("terminal does not support transparency")
        except:
            log.warning("transparency support disabled because cursext module is not present")

    # try disabling cursor
    try:
        curses.curs_set(0)
    except:
        log.warning("terminal does not support disabling of cursor")

    if config.general.mousesupport:
        # enable all mouse events
        curses.mousemask(curses.ALL_MOUSE_EVENTS)

    # redirect stderr to /dev/null (to prevent spoiling the screen
    # with libalsa messages). This is not really nice but at the moment there
    # is no other way to get rid of this nuisance.
    dev_null = file("/dev/null", 'w')
    os.dup2(dev_null.fileno(), sys.stderr.fileno())

    return stdscr

##############################################################################
# ... and cleanup
##############################################################################

def cursescleanup():
    # restore terminal settings
    try:
        stdscr.keypad(0)
        curses.echo()
        curses.nocbreak()
        curses.endwin()
    except:
        pass


##############################################################################
# signal handler
##############################################################################

def sigtermhandler(signum, frame):
    # shutdown all running threads
    hub.notify(events.quit(), 100)

signal.signal(signal.SIGTERM, sigtermhandler)

##############################################################################
# setup main screen (safety wrapped)
##############################################################################

try:
    stdscr = cursessetup()
    # set m to None as marker in case that something goes wrong in the
    # mainscreen.mainscreen constructor
    m = None
    m = mainscreen.mainscreen(stdscr, songdbids, playerids, plugins)
    m.run()
except:
    cursescleanup()

    # shutdown all other threads
    hub.notify(events.quit(), 100)

    helper.print_exc_plus()
    raise
else:
    cursescleanup()

    # shutdown all other threads
    hub.notify(events.quit(), 100)
