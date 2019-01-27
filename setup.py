#!/usr/bin/env python
# -*- coding: ISO-8859-1 -*-

from setuptools import setup, Extension # find_packages
import sys; sys.path.append("src")
from os import path
from version import version

# build extension module which replaces the Python audio output buffer
# by a C version, which should help preventing audio dropouts.
# You need the libao header files for building (but on the other hand,
# you don't need the pyao extension module when you use bufferedao)
buildbufferedaoext = True

# list of supported locales
locales = ["de", "it", "fr", "pl"]


# Get the long description from the README file
here = path.abspath(path.dirname(__file__))
with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

# list of packages
#
packages = ["pytone",
            "pytone.services", "pytone.services.players", "pytone.services.songdbs",
            "pytone.plugins", "pytone.plugins.audioscrobbler"]

#
# list of extension modules to be built
#
ext_modules = [Extension("pytone.pcm", sources=["src/pcm/pcm.c"])]

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

addargs = {"classifiers": classifiers}

setup(name="PyTone",
      version=version,
      description="Powerful music jukebox with a curses based GUI.",
      long_description=long_description,
      long_description_content_type="text/markdown",
      author="Jörg Lehmann",
      author_email="joerg@luga.de",
      url="http://www.luga.de/pytone/",
      license="GPL",
      python_requires="~=3.5",
      install_requires=["mutagen"],
      package_dir={"pytone": "src"},
      packages=packages,
      ext_modules=ext_modules,
      data_files=data_files,
      scripts=scripts,
      **addargs)
