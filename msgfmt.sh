#!/bin/sh

# adjust this path as necessary
GETTEXTPATH=/usr/local/opt/gettext/bin

LOCALES="de it pl fr"

for locale in $LOCALES; do
  echo Compiling locale $locale...
  localedir=locale/$locale/LC_MESSAGES
  $GETTEXTPATH/msgfmt $localedir/PyTone.po -o $localedir/PyTone.mo
done
