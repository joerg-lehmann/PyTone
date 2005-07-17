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

import inspect
import os.path
import sys
import threading
import time
import traceback

_DEBUG   = 0
_INFO    = 1
_WARNING = 2
_ERROR   = 3

_desc = { _DEBUG:   "D",
          _INFO:    "I",
          _WARNING: "W",
          _ERROR:   "E" }

# minimal level of log messages that should be stored in the buffer
# accesible to the user in the messagewin
LOGLEVEL = _INFO
# LOGLEVEL = _DEBUG

# open file for log output, if necessary
debugfile = None

# length of path prefix (used to obtain module name from path)
pathprefixlen = len(os.path.dirname(__file__))

def initdebugfile(debugfilename):
    """ direct debugging output to debugfilename """
    global debugfile
    if debugfilename:
        debugfile = open(debugfilename, "w", 1)

# log buffer consisting of tuples (loglevel, time, logmessage)
items = []

# maximal length of log buffer
maxitems = 100

def log(s, level):
    if debugfile:
        try:
            frame = inspect.stack()
            try:
                timestamp = time.strftime("%H:%M:%S", time.localtime())
                threadname = threading.currentThread().getName()
                modulename = frame[2][1][pathprefixlen+1:-3]
                debugfile.write("%s [%s|%s|%s] %s\n" % (_desc[level], timestamp, threadname, modulename, s))
            finally:
                del frame
        except:
            debugfile.write("%s [???] %s\n" % (_desc[level], s))

    if level >= LOGLEVEL:
        items.append((level, time.time(), s))
        if len(items) > maxitems:
            items.pop(0)

def debug(s):
    log(s, _DEBUG)

def info(s):
    log(s, _INFO)

def warning(s):
    log(s, _WARNING)

def error(s):
    log(s, _ERROR)

def debug_traceback():
    debug("Exception caught: %s " % sys.exc_info()[1])
    tblist = traceback.extract_tb(sys.exc_info()[2])
    for s in traceback.format_list(tblist):
        debug(s[:-1])


