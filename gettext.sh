#!/bin/sh

POTFILE=locale/PyTone.pot
LOCALES="de it pl fr"

# Adjust the following paths as necessary
PYGETTEXTPATH=/Library/Frameworks/Python.framework/Versions/3.7/share/doc/python3.7/examples/Tools/i18n
GETTEXTPATH=/usr/local/opt/gettext/bin

$PYGETTEXTPATH/pygettext.py -o $POTFILE src/*.py src/services/*.py src/services/songdbs/*.py src/services/players/*.py
for locale in $LOCALES; do
  echo Processing locale $locale...
  localedir=locale/$locale/LC_MESSAGES
  $GETTEXTPATH/msgmerge $localedir/PyTone.po $POTFILE -o $localedir/PyTone.po.new
  mv $localedir/PyTone.po $localedir/PyTone.po.old
  mv $localedir/PyTone.po.new $localedir/PyTone.po
done
