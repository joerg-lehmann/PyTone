# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2003 Jörg Lehmann <joerg@luga.de>
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

import ConfigParser, copy, curses, sys, getopt, exceptions, os.path, types, re, types
import log, version


class ConfigError(exceptions.Exception):
    pass


class configsection:

    """section of the config file"""

    # we store our configuration items in a separate dictionary _configitems
    # after instantiation, we only allow reading and writing to this
    # dictionary (via the corresponding configitems get and set method)
    def __getattr__(self, name):
        try:
            return self._configitems[name].get()
        except KeyError:
            raise AttributeError
            try:
                return self._configsections[name]
            except KeyError:
                raise AttributeError

    def __setattr__(self, name, value):
        self._configitems[name].set(value)

    def __delattr__(self, name):
        del self._configitems[name]

    def __getitem__(self, name):
        try:
            return self._configitems[name].get()
        except KeyError:
            try:
                return self._configsections[name]
            except KeyError:
                raise IndexError

    def asdict(self):
        d = {}
        for n, v in self._configitems.items():
            d[n] = v
        return d

    def getsubsections(self):
        return self._configsections.keys()

#
# define different types of configuration variables
#

class configitem:
    def __init__(self, default):
        self._check(default)
        self.default = default
        self.value = None
        # cached effective output value
        self._cachedoutput = None

    def _check(self, s):
        """ check whether string conforms with expected format
        If not, this method should raise a ConfigError exception.
        """
        pass

    def _convert(self, s):
        """ convert from string to item value """
        return s

    def set(self, s):
        self._check(s)
        self.value = s
        self._cachedoutput = None

    def get(self):
        if self._cachedoutput is None:
            if self.value is None:
                self._cachedoutput = self._convert(self.default)
            else:
                self._cachedoutput = self._convert(self.value)
        return self._cachedoutput

class configstring(configitem):
    pass


class configint(configitem):
    def _check(self, s):
        try:
            int(s)
        except:
            raise ConfigError("Expecting float, got '%s'" % s)

    def _convert(self, s):
        return int(s)


class configfloat(configitem):
    def _check(self, s):
        try:
            float(s)
        except:
            raise ConfigError("Expecting float, got '%s'" % s)

    def _convert(self, s):
        return float(s)


class configlist(configitem):
    def _check(self, s):
        try:
            items = s.split()
        except:
            raise ConfigError("Expecting list, got '%s'" % s)

    def _convert(self, s):
        return s.split()


class configcolor(configitem):

    # dict of available curses colors
    #
    # The entry for "default" is set to -1 (in mainscreen.py) if the
    # curses.use_default_colors() call succeeds. It then represents a
    # (possibly transpert) default color.

    _colors = { "white": curses.COLOR_WHITE,
                "black": curses.COLOR_BLACK,
                "green": curses.COLOR_GREEN,
                "magenta": curses.COLOR_MAGENTA,
                "blue": curses.COLOR_BLUE,
                "cyan": curses.COLOR_CYAN,
                "yellow": curses.COLOR_YELLOW,
                "red": curses.COLOR_RED,
                "default" : 0 }

    _mono = { "none": curses.A_NORMAL,
              "bold": curses.A_BOLD,
              "underline": curses.A_UNDERLINE,
              "reverse": curses.A_REVERSE,
              "standout": curses.A_STANDOUT }

    _defaultbg = "default"

    # disable color support by default. Reenable it in mainscreen.py
    # if supported by terminal
    _colorenabled = 0

    _colorpairs = []

    # two helper methods which parse a color or a mono definition
    # and return the rest of the line

    def _parsecolor(self, cdef):
        if cdef[1].startswith("bright"):
            fg = self._colors[cdef[1][6:]]
            bright = 1
        else:
            fg = self._colors[cdef[1]]
            bright = 0
        if len(cdef)>2 and cdef[2]!="mono":
            bg = self._colors[cdef[2]]
            return ((fg, bg, bright), cdef[3:])
        else:
            bg = self._colors[self._defaultbg]
            return ((fg, bg, bright), cdef[2:])

    def _parsemono(self, cdef):
        attr = cdef[1]
        return (self._mono[attr], cdef[2:])

    def _parsecolormono(self, cdef):
        # parse combined color and mono definition
        fg = bg = bright = attr = None
        if cdef[0] == "color":
            (fg, bg, bright), cdef = self._parsecolor(cdef)
            if cdef:
                attr, cdef = self._parsemono(cdef)
            else:
                attr = self._mono["none"]
        elif cdef[0] == "mono":
            attr, cdef = self._parsemono(cdef)
            if cdef:
                (fg, bg, bright), cdef = self._parsecolor(cdef)
        if cdef:
            raise ConfigError("color definition too long")
        return fg, bg, bright, attr

    def _check(self, s):
        try:
            self._parsecolormono(s.split())
        except:
            raise ConfigError("wrong color definition '%s'" %s )

    def _convert(self, s):
        fg, bg, bright, attr = self._parsecolormono(s.split())
        if fg is not None and self._colorenabled or attr is None:
            try:
                colorindex = self._colorpairs.index((fg, bg))+1
            except ValueError:
                self._colorpairs.append((fg, bg))
                colorindex = len(self._colorpairs)
                curses.init_pair(colorindex, fg, bg)
            color = curses.color_pair(colorindex)
            if bright:
                color |= curses.A_BOLD
            return color
        else:
            return attr

class configkeys(configitem):

    def _check(self, s):
        for key in s.split(" "):
            keyorig = key
            if key[:5].lower()=="ctrl-":
                key = key[5:].upper()
            elif key[:4].lower()=="alt-":
                key = key[4:]
            if key=="KEY_SPACE":
               pass
            elif key.startswith("KEY_") and key[4:].isalnum():
                try:
                    eval("curses.%s" % key)
                except:
                    raise ConfigError("wrong key specification '%s'" % keyorig)
            elif key.startswith("\\") and len(key)==2 and key[1] in ("n", "r", "t"):
                pass
            elif len(key)!=1:
                raise ConfigError("wrong key specification '%s'" % keyorig)

    def _convert(self, s):
        keys = []
        for key in s.split(" "):
            modifier = 0
            if key[:5].lower()=="ctrl-":
                key = key[5:].upper()
                modifier = -64
            elif key[:4].lower()=="alt-":
                key = key[4:]
                modifier = 1024
            if key=="KEY_SPACE":
                keyvalue = 32
            elif key.startswith("KEY_") and key[4:].isalnum():
                keyvalue = eval("curses.%s" % key)
            elif key.startswith("\\") and len(key)==2:
                keyvalue = ord({"n": "\n", "r": "\r", "t": "\t"}[key[1]])
            elif len(key)==1:
                keyvalue = ord(key)
            keys.append(keyvalue+modifier)
        return keys


class configboolean(configitem):
    def _check(self, s):
        if s not in ("0", "1", "on", "off", "true", "false"):
            raise ConfigError("Excepting boolean, got '%s'" % s)

    def _convert(self, s):
        return s in ("1", "on", "true")


class configalternatives(configitem):
    def __init__(self, default, alternatives):
        self.alternatives = alternatives
        configitem.__init__(self, default)

    def _check(self, s):
        if s not in self.alternatives:
            raise ConfigError("Expecting one of %s, got %s" % (str(self.alternatives), s))


class configpath(configitem):
    def _convert(self, s):
        return os.path.expanduser(s)


class confignetworklocation(configitem):

    def _parselocation(self, s):
        if ":" in s:
            # address:port
            name, port = s.split(":")
            port = int(port)
            return name, port
        else:
            return os.path.expanduser(s)

    def _check(self, s):
        try:
            self._parselocation(s)
        except:
            raise ConfigError("Excepting address:port or filename, got '%s'" % s)            

    def _convert(self, s):
        return self._parselocation(s)
 

class configre(configitem):
    def _convert(self, s):
        return re.compile(s)




BORDER_TOP = 1
BORDER_BOTTOM = 2
BORDER_LEFT = 4
BORDER_RIGHT = 8
BORDER_COMPACT = 16
BORDER_ULTRACOMPACT = 32

class configborder(configitem):
    def _check(self, s):
        if s == "all" or s == "compact" or s == "off" or s == "ultracompact":
            return
        for b in s.split():
            if b not in ("top", "bottom", "left", "right", "compact"):
                raise ConfigError("Expecting one of 'top', 'bottom', 'left', or 'right', got '%s'" % b)
    def _convert(self, s):
        result = 0
        if s == "all":
            return BORDER_TOP | BORDER_BOTTOM | BORDER_LEFT | BORDER_RIGHT
        if s == "compact":
            return BORDER_COMPACT
        if s == "off":
            return 0
        if s == "ultracompact":
            return BORDER_ULTRACOMPACT
        for b in s.split():
            if b == "top":
                result |= BORDER_TOP
            elif b == "bottom":
                result |= BORDER_BOTTOM
            elif b == "left":
                result |= BORDER_LEFT
            elif b == "right":
                result |= BORDER_RIGHT
        return result

##############################################################################
# configuration tree
##############################################################################

class general(configsection):
    logfile = configpath("~/.pytone/pytone.log")
    songchangecommand = configstring("")
    playerinfofile = configpath("~/.pytone/playerinfo")
    dumpfile = configpath("~/.pytone/pytone.dump")
    debugfile = configpath("")
    playlistdir = configpath("/mnt/mp3/playlists")
    randominsertlength = configfloat("3600")
    colorsupport = configalternatives("auto", ["auto", "on", "off"])
    layout = configalternatives("twocolumn", ["onecolumn", "twocolumn"])
    throttleoutput = configint("0")
    autoplaymode = configalternatives("off", ["off", "repeat", "random"])
    plugins = configlist("")

class database(configsection):
    class __template__(configsection):
        type = configalternatives("local", ["local", "remote"])
        basename = configpath("~/.pytone/mp3")
        dbenvdir = configpath("~/.pytone/mp3")
        dbfile = configpath("")
        cachesize = configint("1000")
        musicbasedir = configpath("")
        tracknrandtitlere = configre(r"^\[?(\d+)\]? ?[- ] ?(.*)\.(mp3|ogg)$")
        tags_capitalize = configboolean("true")
        tags_stripleadingarticle = configboolean("true")
        tags_removeaccents = configboolean("true")
        autoregisterer = configboolean("on")
        playingstatslength = configint("100")
        networklocation = confignetworklocation("localhost:1972")

class mixer(configsection):
    device = configpath("/dev/mixer")
    channel = configstring("SOUND_MIXER_PCM")
    stepsize = configint("5")

class network(configsection):
    socketfile = configstring("~/.pytone/pytonectl")
    enableserver = configboolean("false")
    bind = configstring("")
    port = configint("1972")

class player(configsection):
    class main(configsection):
        type = configalternatives("internal", ["internal", "xmms", "mpg123", "remote", "off"])
        autoplay = configboolean("true")

        # only for internal player
        driver = configalternatives("oss", ["alsa", "alsa09", "arts", "esd", "oss", "sun"])
        device = configstring("/dev/dsp")
        bufsize = configint(100)
        crossfading = configboolean("true")
        crossfadingstart = configfloat(5)
        crossfadingduration = configfloat(6)
        aooptions = configstring("")

        # only for xmms player
        session = configint("0")
        noqueue = configboolean("false")

        # only for mpg123 player
        cmdline = configstring("/usr/bin/mpg321 --skip-printing-frames=5 -a /dev/dsp")

        # only for remote player
        networklocation = confignetworklocation("localhost:1972")

    class secondary(configsection):
        type = configalternatives("off", ["internal", "xmms", "mpg123", "off"])
        autoplay = configboolean("true")

        # only for internal player
        driver = configalternatives("oss", ["alsa", "alsa09", "arts", "esd", "oss", "sun"])
        device = configstring("/dev/dsp1")
        bufsize = configint(100)
        crossfading = configboolean("true")
        crossfadingstart = configfloat(5)
        crossfadingduration = configfloat(6)
        aooptions = configstring("")

        # only for xmms player
        session = configint("0")
        noqueue = configboolean("false")

        # only for mpg123 player
        cmdline = configstring("/usr/bin/mpg321 --skip-printing-frames=5 -a /dev/dsp1")

class filelistwindow(configsection):
    border = configborder("all")
    scrollbar = configboolean("true")
    scrollmode = configalternatives("page", ["page", "line"])
    virtualdirectoriesattop = configboolean("false")
    skipsinglealbums = configboolean("true")


class playerwindow(configsection):
    border = configborder("all")
    songformat = configstring("%(artist)s - %(title)s")


class iteminfowindow(configsection):
    border = configborder("all")


class playlistwindow(configsection):
    border = configborder("all")
    scrollbar = configboolean("true")
    scrollmode = configalternatives("page", ["page", "line"])
    songformat = configstring("%(artist)s - %(title)s")


class mixerwindow(configsection):
    type = configalternatives("popup", ["popup", "statusbar"])
    autoclosetime = configfloat("5")


class helpwindow(configsection):
    autoclosetime = configfloat("10")


class logwindow(configsection):
    autoclosetime = configfloat("10")


class iteminfolongwindow(configsection):
    autoclosetime = configfloat("10")


class inputwindow(configsection):
    type = configalternatives("popup", ["popup", "statusbar"])


class colors(configsection):
    class filelistwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        activetitle = configcolor("color brightgreen mono bold")
        background = configcolor("color white")
        selected_song = configcolor("color white red mono reverse")
        artist_album = configcolor("color brightblue mono bold")
        directory = configcolor("color brightcyan mono bold")
        border = configcolor("color green")
        activeborder = configcolor("color brightgreen mono bold")
        scrollbar = configcolor("color green")
        scrollbarhigh = configcolor("color brightgreen mono bold")
        scrollbararrow = configcolor("color brightgreen mono bold")
        song = configcolor("color white")
        selected_directory = configcolor("color brightcyan red mono reverse")
        selected_artist_album = configcolor("color brightblue red mono reverse")

    class playlistwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        activetitle = configcolor("color brightgreen mono bold")
        background = configcolor("color white")
        unplayedsong = configcolor("color brightwhite mono bold")
        selected_unplayedsong = configcolor("color brightwhite red mono reverse")
        playedsong = configcolor("color white")
        selected_playedsong = configcolor("color white red mono reverse")
        playingsong = configcolor("color yellow mono underline")
        selected_playingsong = configcolor("color yellow red mono reverse")
        border = configcolor("color green")
        activeborder = configcolor("color brightgreen mono bold")
        scrollbar = configcolor("color green")
        scrollbarhigh = configcolor("color brightgreen mono bold")
        scrollbararrow = configcolor("color brightgreen mono bold")

    class playerwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        content = configcolor("color white")
        background = configcolor("color white")
        description = configcolor("color brightcyan mono bold")
        activeborder = configcolor("color brightgreen mono bold")
        progressbar = configcolor("color cyan cyan")
        border = configcolor("color green")
        progressbarhigh = configcolor("color red red mono bold")

    class iteminfowindow(configsection):
        title = configcolor("color brightgreen mono bold")
        content = configcolor("color white")
        background = configcolor("color white")
        description = configcolor("color brightcyan mono bold")
        activeborder = configcolor("color brightgreen mono bold")
        border = configcolor("color green")

    class iteminfolongwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        content = configcolor("color white")
        background = configcolor("color white")
        description = configcolor("color brightcyan mono bold")
        activeborder = configcolor("color brightgreen mono bold")
        border = configcolor("color green")

    class inputwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        content = configcolor("color white")
        background = configcolor("color white")
        description = configcolor("color brightcyan mono bold")
        activeborder = configcolor("color brightgreen mono bold")
        border = configcolor("color green")

    class mixerwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        content = configcolor("color white")
        bar = configcolor("color cyan cyan")
        description = configcolor("color brightcyan mono bold")
        border = configcolor("color green")
        background = configcolor("color white")
        activeborder = configcolor("color brightgreen mono bold")
        barhigh = configcolor("color red red mono bold")

    class helpwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        background = configcolor("color white")
        key = configcolor("color brightcyan mono bold")
        description = configcolor("color white")
        activeborder = configcolor("color brightgreen mono bold")
        border = configcolor("color green")

    class logwindow(configsection):
        title = configcolor("color brightgreen mono bold")
        background = configcolor("color white")
        time = configcolor("color brightcyan mono bold")
        debug = configcolor("color white")
        info = configcolor("color white")
        warning = configcolor("color cyan")
        error = configcolor("color red mono bold")
        activeborder = configcolor("color brightgreen mono bold")
        border = configcolor("color green")

    class statusbar(configsection):
        key = configcolor("color brightcyan mono bold")
        background = configcolor("color white")
        description = configcolor("color white")


class keybindings(configsection):
    class general(configsection):
        refresh = configkeys("ctrl-l")
        exit = configkeys("ctrl-x")
        playerstart = configkeys("p P")
        playerpause = configkeys("p P")
        playernextsong = configkeys("n N")
        playerprevioussong = configkeys("b B")
        playerforward = configkeys(">")
        playerrewind = configkeys("<")
        playerstop = configkeys("S")
        playlistdeleteplayedsongs = configkeys("KEY_BACKSPACE")
        playlistclear = configkeys("ctrl-d")
        playlistsave = configkeys("ctrl-w")
        playlistload = configkeys("ctrl-r")
        playlistreplay = configkeys("ctrl-u")
        playlisttoggleautoplaymode = configkeys("ctrl-t")
        togglelayout = configkeys("KEY_F10")
        showhelp = configkeys("?")
        showlog = configkeys("!")
        showiteminfolong = configkeys("=")
        toggleiteminfowindow = configkeys("ctrl-v")
        volumeup = configkeys(")")
        volumedown = configkeys("(")

    class filelistwindow(configsection):
        selectnext = configkeys("KEY_DOWN j")
        selectprev = configkeys("KEY_UP k")
        selectnextpage = configkeys("ctrl-n KEY_NPAGE")
        selectprevpage = configkeys("ctrl-p KEY_PPAGE")
        selectfirst = configkeys("ctrl-a KEY_HOME")
        selectlast = configkeys("ctrl-e KEY_END")
        dirdown = configkeys("KEY_RIGHT KEY_SPACE \n KEY_ENTER l")
        dirup = configkeys("KEY_LEFT h")
        addsongtoplaylist = configkeys("KEY_SPACE \n KEY_ENTER KEY_RIGHT")
        adddirtoplaylist = configkeys("i I KEY_IC alt-KEY_RIGHT")
        playselectedsong = configkeys("alt-\n alt-KEY_ENTER")
        activateplaylist = configkeys("\t")
        insertrandomlist = configkeys("r R")
        rescan = configkeys("u U")
        search = configkeys("/ ctrl-s")
        repeatsearch = configkeys("ctrl-g")

    class playlistwindow(configsection):
        selectnext = configkeys("KEY_DOWN j")
        selectprev = configkeys("KEY_UP k")
        selectnextpage = configkeys("ctrl-n KEY_NPAGE")
        selectprevpage = configkeys("ctrl-p KEY_PPAGE")
        selectfirst = configkeys("ctrl-a KEY_HOME")
        selectlast = configkeys("ctrl-e KEY_END")
        moveitemup = configkeys("+")
        moveitemdown = configkeys("-")
        deleteitem = configkeys("d D KEY_DC")
        activatefilelist = configkeys("\t KEY_LEFT h")
        playselectedsong = configkeys("alt-\n alt-KEY_ENTER")
        rescan = configkeys("u U")
        shuffle = configkeys("r R")
        filelistjumptoselectedsong = configkeys("KEY_RIGHT l")

#
# register known configuration sections
#

sections = ['mixerwindow', 'helpwindow', 'filelistwindow', 'database', 'iteminfowindow',
            'logwindow', 'iteminfolongwindow', 'mixer', 'colors', 'playerwindow', 'playlistwindow',
            'general', 'inputwindow', 'network', 'player', 'keybindings']

##############################################################################
# end configuration tree
##############################################################################

# options which can be overwritten via the command line

userconfigfile = os.path.expanduser("~/.pytone/pytonerc")
forcedatabaserebuild = False
forcedebugfile = None

#
# helper functions
#

# configparser used for the config files
configparser = None

def setupconfigparser():
    """ initialize ConfigParser.RawConfigParser for the standard configuration files """
    global configparser
    cflist = ["/etc/pytonerc", userconfigfile]
    s = ", ".join(map(os.path.realpath, cflist))
    log.info("Using configuration from file(s) %s" % s)
    configparser = ConfigParser.RawConfigParser()
    configparser.read(cflist)


def readconfigsection(section, clsection):
    """ fill configsection subclass clsection with entries stored under the name section in configfile and
    return a corresponding clsection instance"""
    try:
        for option in configparser.options(section):
            if not clsection.__dict__.has_key(option):
                raise ConfigError("Unkown configuration option '%s' in section '%s'" %
                                  (option, section))
            value = configparser.get(section, option)
            clsection.__dict__[option].set(value)
    except ConfigParser.NoSectionError:
        pass


def finishconfigsection(clsection):
    """ finish a configsection subclass clsection """
    # move configuration items from class __dict__ into _configitems and store
    # config subsections
    clsection._configitems = {}
    clsection._configsections = {}
    for n, v in clsection.__dict__.items():
        if isinstance(v, configitem):
            clsection._configitems[n] = v
            del clsection.__dict__[n]
        elif type(v) == types.ClassType and issubclass(v, configsection) and n != "__template__":
            finishconfigsection(v)
            # instantiate class to make __getattr__ and __setattr__ work and add the instance to
            # a _configsections dictionary
            clsection.__dict__[n] = clsection._configsections[n] = v()


def processstandardconfig():
    for section in configparser.sections():
        if not section.startswith("plugin."):
            if "." not in section:
                # not a subsection
                if section not in sections:
                    raise ConfigError("Unkown configuration section '%s'" % section)
            else:
                # check for valid subsection
                # first check the form (section.subsection) of the config section
                try:
                    mainsection, subsection = section.split(".")
                except:
                    raise ConfigError("Unkown configuration section '%s'" % section)
                if mainsection not in sections or not subsection.isalnum():
                    raise ConfigError("Unkown configuration section '%s'" % section)
                # get corresponding config class
                try:
                    clsection = eval(section)
                    if not issubclass(clsection, configsection):
                        raise ConfigError("Unkown configuration section '%s'" % section)
                except AttributeError:
                    # if it does not exist, use a __template__ class in
                    # mainsection if possible
                    try:
                        # We copy the __template__ class by explicitely
                        # creating a new class with a deeply copied class
                        # dictionary (maybe there is an easier solution)
                        # Any
                        templateclassdict = eval("%s.__template__.__dict__" % mainsection)
                        newclass = types.ClassType(mainsection+subsection, (configsection,), copy.deepcopy(templateclassdict))
                        exec("%s.%s = newclass" % (mainsection, subsection))
                    except AttributeError:
                        raise ConfigError("Unkown configuration section '%s'" % section)

            readconfigsection(section, eval(section))


def finishconfig():
    """ prepare all configuration sections for later use and read command line arguments """

    for section in sections:
        finishconfigsection(eval(section))

        # convert the configsection class into an instance of the same class
        # to make __getattr__ and __setattr__ work
        exec("%s = %s()" % (section, section)) in globals(), globals()

    # apply command line options
    if forcedatabaserebuild:
        for databasename in database.getsubsections():
            exec("database.%s.autoregisterer = 'on'" % databasename) in globals(), globals()

    if forcedebugfile:
        general.debugfile = forcedebugfile


def gendefault():
    cp = ConfigParser()
    cp.read("/home/ringo/PyTone/config")
    for section in cp.sections():
        print "class %s(configsection):" % section
        for option in cp.options(section):
            default = cp.get(section, option)

            if option.startswith("color_"):
                itemname = "configcolor"
            elif default in ("on", "off", "true", "false"):
                itemname = "configboolean"
            else:
                try:
                    float(default)
                    itemname = "configfloat"
                except:
                    itemname = "configstring"

            print '    %s = %s("%s")' % (option, itemname, default)
        print

    print "sections =", cp.sections()

#
# parse command line options
#

def usage():
    print "PyTone %s" % version.version
    print "Copyright %s" % version.copyright
    print "usage: pytone.py [options]"
    print "-h, --help: show this help"
    print "-c, --config <filename>: read config from filename"
    print "-d, --debug <filename>: enable debugging output (into filename)"
    print "-r, --rebuild: rebuild all databases"


def processcommandline():
    # we pass the information on the command line options via
    # global variables
    global userconfigfile
    global forcedatabaserebuild
    global forcedebugfile
    try:
        # keep rest of arguments for other use
        global args
        opts, args = getopt.getopt(sys.argv[1:],
                                   "hc:d:r",
                                   ["help", "config=", "debug=", "rebuild"])
    except getopt.GetoptError:
        usage()
        sys.exit(2)

    for o, a in opts:
        if o in ("-h", "--help"):
            usage()
            sys.exit()
        if o in ("-d", "--debug"):
            forcedebugfile = a
        if o in ("-c", "--config"):
            userconfigfile = a
        if o in ("-r", "--rebuild"):
            forcedatabaserebuild = True


def checkoptions():
    #if network.enableserver and network.server:
    #    usage()
    #    print "Error: cannot run both as server and as client"
    #    sys.exit(2)


    # check database options
    basenames = []
    dbenvdirs = []

    if not database.getsubsections():
        print "Please define at least one song database in your configuration file."
        sys.exit(2)

    for databasename in database.getsubsections():
        songdb = database[databasename]

        if songdb == "local" and songdb.musicbasedir == "":
            print ( "Please set musicbasedir in the [database.%s] section of the config file pytonerc\n"
                    "to the location of your MP3/Ogg Vorbis files." % databasename )
            sys.exit(2)

        if songdb.type=="local" and not (songdb.dbfile != "" and songdb.basename == "" or
                                         songdb.dbfile == "" and songdb.basename != ""):
            print "Please use either the dbfile or the basename option (not both) to specify the location of your song database '%s'." % databasename
            sys.exit(2)

        if songdb.basename != "":
            if songdb.basename in basenames:
                print "basename '%s' of database '%s' already in use." % (songdb.basename, databasename)
                sys.exit(2)
            basenames.append(songdb.basename)

        if songdb.dbfile != "":
            if songdb.dbenvdir in dbenvdirs:
                print "dbenvdir '%s' of database '%s' already in use." % (songdb.dbenvdir, databasename)
                sys.exit(2)
            dbenvdirs.append(songdb.dbenvdir)

    # check whether oss module is present
    try:
        import ossaudiodev
    except:
        try:
            import oss
        except:
            mixer.device = ""
            log.warning("disabling mixer since neither ossaudiodev nor oss module is installed")

    # check ao options
    for aooption in player.main.aooptions.split() + player.secondary.aooptions.split():
        if aooption.count("=")!=1:
            raise RuntimeError("invalid format for alsa option '%s'" % aooption)


def processconfig():
    setupconfigparser()
    processstandardconfig()
    finishconfig()
    checkoptions()
