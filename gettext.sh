#!/bin/sh

POTFILE=locale/PyTone.pot
LOCALES="de it pl fr"

pygettext.py -o $POTFILE src/*.py src/services/*.py src/services/songdbs/*.py src/services/players/*.py
for locale in $LOCALES; do
  echo Processing locale $locale...
  localedir=locale/$locale/LC_MESSAGES
  msgmerge $localedir/PyTone.po $POTFILE -o $localedir/PyTone.po.new
  mv $localedir/PyTone.po $localedir/PyTone.po.old
  mv $localedir/PyTone.po.new $localedir/PyTone.po
done
