#!/bin/sh

LOCALES="de it pl fr"

for locale in $LOCALES; do
  echo Compiling locale $locale...
  localedir=locale/$locale/LC_MESSAGES
  msgfmt $localedir/PyTone.po -o $localedir/PyTone.mo
done
