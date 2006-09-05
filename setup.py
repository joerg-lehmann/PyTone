#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-
from distutils.core import setup, Extension
import sys; sys.path.append("src")
from version import version

# build extension module which adds transparency support for terminals
# supporting this feature (not necessary for Python 2.4 and above)
# You need the curses header files for building
buildcursext = False

# build extension module which replaces the Python audio output buffer
# by a C version, which should help preventing audio dropouts.
# You need the libao header files for building (but on the other hand,
# you don't need the pyao extension module when you use bufferedao)
buildbufferedaoext = True

# list of supported locales
locales = ["de", "it", "fr", "pl"]

#
# list of packages
#
packages = ["pytone",
            "pytone.services", "pytone.services.players", "pytone.services.songdbs",
            "pytone.plugins", "pytone.plugins.audioscrobbler"]

#
# list of extension modules to be built
#
ext_modules = [Extension("pytone.pcm", sources=["src/pcm/pcm.c"])]

if buildcursext:
    ext_modules.append(Extension("pytone.cursext",
                                 sources=["src/cursext/cursextmodule.c"],
                                 libraries=["curses"]))


if buildbufferedaoext:
    ext_modules.append(Extension("pytone.bufferedao",
                                 sources=["src/bufferedao.c"],
                                 libraries=["ao"]))
#
# list of data files to be installed
#
mo_files = ["locale/%s/LC_MESSAGES/PyTone.mo" % locale for locale in locales]
data_files=[('share/locale/de/LC_MESSAGES', mo_files)]

#
# list of scripts to be installed
#
# Note that we (ab-)use distutils scripts option to install our wrapper
# files (hopefully) at the correct location.
scripts=['pytone', 'pytonectl']

#
# additional package metadata
#
classifiers = ["Development Status :: 5 - Production/Stable",
               "Environment :: Console :: Curses",
               "Intended Audience :: End Users/Desktop",
               "License :: OSI Approved :: GNU General Public License (GPL)",
               "Programming Language :: Python",
               "Topic :: Multimedia :: Sound/Audio :: Players"]

if sys.version_info >= (2, 3):
    addargs = {"classifiers": classifiers}
else:
    addargs = {}

setup(name="PyTone",
      version=version,
      description="Powerful music jukebox with a curses based GUI.",
      author="Jörg Lehmann",
      author_email="joerg@luga.de",
      url="http://www.luga.de/pytone/",
      license="GPL",
      package_dir={"pytone": "src"},
      packages=packages,
      ext_modules=ext_modules,
      data_files=data_files,
      scripts=scripts,
      **addargs)
