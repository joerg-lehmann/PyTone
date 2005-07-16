# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004 Jörg Lehmann <joerg@luga.de>
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

import re
import events, hub

class slist:
    """ Generic list class with selectable items

    List with selectable items, out of which maximally height are
    being displayed at the same time.

    If window corresponding to list has focus, selectionchanged events
    are issued upon change of the currently selected item.
    """

    def __init__(self, win, pagescroll):
        self.win = win
        self.items = []
        self.selected = None   # currently selected item
        self.top = 0           # first displayed item
        self.pagescroll = pagescroll

    # generic list methods

    def __getitem__(self, key):
        return self.items[key]

    def __len__(self):
        return len(self.items)

    def __delitem__(self, index):
        del self.items[index]
        if self.selected is not None:
            if len(self) == 0:
                self.selected = None
            else:
                if index < self.selected:
                    self.selected -= 1
                self.selected = min(self.selected, len(self)-1)
            self._notifyselectionchanged()
        self._updatetop()

    def index(self, item):
        return self.items.index(item)

    def insert(self, index, item):
        self.items.insert(index, item)
        if self.selected is None:
            self.selected = 0
            self._notifyselectionchanged()
        elif self.selected>=index:
            self.selected += 1
            self._notifyselectionchanged()
        self._updatetop()

    def append(self, item):
        self.items.append(item)
        if self.selected is None:
            self.selected = 0
            self._notifyselectionchanged()
        self._updatetop()

    def remove(self, item):
        for i in range(len(self)):
            if self[i] is item:
                del self[i]
                return

    def set(self, items, keepselection=False):
        """set all items in slist trying to keep the current selection if keepselection is set """
        if keepselection:
            oldselecteditem = self.getselected()
            oldselected = self.selected
        try:
            self.items = list(items)
        except:
            self.items = []
        if keepselection and oldselected is not None and self.items:
            # we try to keep the current selection and search for the previously
            # selected item in the new list. We most probably find it around
            # the original position.
            oldselecteditemid = oldselecteditem.getid()
            startsearch = min(max(0, oldselected-1), len(self))
            for i in range(startsearch, len(self)) + range(startsearch):
                if self[i].getid() == oldselecteditemid:
                    self.selected = i
                    break
            else:
                # if this fails (typically because the song has been
                # deleted from the playlist), we take the item at the
                # last selected position, if possible
                if oldselected < len(self):
                    self.selected = oldselected
                elif len(self) > 0:
                    self.selected = len(self)-1
            self._updatetop()
        else:
            if self.items:
                self.selected = 0
            else:
                self.selected = None
            self.top = 0
        self._notifyselectionchanged()

    def sort(self, func=None):
        if func is None:
            self.items.sort()
        else:
            self.items.sort(func)
        self._notifyselectionchanged()

    # helper routines

    def _notifyselectionchanged(self):
        """ helper routine, which issues a selectionchanged event, if window
        corresponding to list has focus """

        if self.win.hasfocus():
            hub.notify(events.selectionchanged(self.getselected()))

    def _updatetop(self):
        "helper routine, which updates self.top"

        if len(self)<=self.win.ih:
            self.top = 0
            return

        if self.selected is not None and self.selected<self.top:
            if self.pagescroll:
                self.top = max(0, self.selected-self.win.ih+1)
            else:
                self.top = self.selected
            return

        if self.selected is not None and self.selected>self.top+self.win.ih-1:
            if self.pagescroll:
                self.top = self.selected
            else:
                self.top = self.selected-self.win.ih+1
            return

    # slist specific methods

    def clear(self):
        "clear list"
        self.items = []
        self.selected = None
        self.top = 0
        self._notifyselectionchanged()

    def insertitem(self, item, cmpfunc):
        "insert item at alphabetically correct position"
        for i in range(len(self)):
            if cmpfunc(self[i], item)>=0:
                self.insert(i, item)
                break
        else:
            self.append(item)

    def getselected(self):
        "return currently selected item"
        if self.selected is not None:
            try:
                return self.items[self.selected]
            except IndexError:
                if self.items:
                    self.selected = len(self.items)-1
                    return self.items[self.selected]
                else:
                    self.selected = None
        return None

    def deleteselected(self):
        "delete currently selected item"
        if self.selected is not None:
            del self[self.selected]

    def selectbynr(self, nr):
        "select nrth entry in list"
        self.selected = nr
        self._notifyselectionchanged()
        self._updatetop()

    def selectbylinenumber(self, nr):
        """select entry by line number in window
        Returns True if selection was valid, otherwise False.
        """
        if len(self) > 0:
            if nr >= 0 and self.top+nr < len(self):
                self.selected = self.top+nr
                self._notifyselectionchanged()
                return True
        return False

    def selectbyname(self, name):
        """select entry by name
        Returns True if selection was valid, otherwise False."""
        if len(self) > 0:
            for i in range(len(self)):
                if self[i].name == name:
                    self.selected = i
                    self._notifyselectionchanged()
                    self._updatetop()
                    return True
        return False

    def selectbysearchstring(self, searchstring):
        """select next entry matching searchstring.
        Returns True if selection was valid, otherwise False."""
        if len(self) > 0:
            searchstring = searchstring.lower()
            if self.selected is None:
                first = 0
            else:
                first = self.selected
            for i in range(first+1, len(self)) + range(first):
                if self[i].getname().lower().find(searchstring)!=-1:
                    self.selected = i
                    self._notifyselectionchanged()
                    self._updatetop()
                    return True
        return False

    def selectbyregexp(self, regexp, includeselected=True):
        """select next entry matching regexp
        Returns True if selection was valid, otherwise False."""
        if len(self) > 0:
            try:
                cregexp = re.compile(regexp, re.IGNORECASE)
            except:
                return
            if self.selected is None:
                first = 0
            else:
                first = self.selected
            for i in range(first + (not includeselected and 1 or 0), len(self)) + range(first):
                if cregexp.search(self[i].getname()):
                    self.selected = i
                    self._notifyselectionchanged()
                    self._updatetop()
                    return True
        return False

    def selectbyletter(self, letter):
        """select next entry beginning with letter
        Returns True if selection was valid, otherwise False."""
        if len(self)>0:
            if self.selected is None:
                first = 0
            else:
                first = self.selected
                letter = letter.lower()
                for i in range(first+1, len(self)) + range(first):
                    if self[i].getname().lower().startswith(letter):
                        self.selected = i
                        self._notifyselectionchanged()
                        self._updatetop()
                        return True
        return False

    def selectrelative(self, dist):
        "change selection relatively by dist"
        if len(self) > 0:
            self.selected += dist
            self.selected = max(self.selected,0)
            self.selected = min(self.selected, len(self)-1)
            self._notifyselectionchanged()
            self._updatetop()

    def selectfirst(self):
        "select first item of list"
        if len(self) > 0:
            self.selected = 0
            self._notifyselectionchanged()
            self._updatetop()

    def selectlast(self):
        "select last item of list"
        if len(self) > 0:
            self.selected = len(self)-1
            self._notifyselectionchanged()
            self._updatetop()

    def selectnext(self):
        "select next item of list"
        self.selectrelative(1)

    def selectprev(self):
        "select previous item of list"
        self.selectrelative(-1)

    def selectnextpage(self):
        "select next page of list"
        self.selectrelative(self.win.ih)

    def selectprevpage(self):
        "select previous page of list"
        if len(self) > 0:
            if self.top-self.win.ih >= 0:
                self.top = self.top-self.win.ih
                self.selected = min(self.top+self.win.ih-1, len(self)-1)
            else:
                self.top = self.selected = 0
            self._notifyselectionchanged()

    def moveitemup(self):
        "move selected item up, if not first"
        if self.selected is not None and self.selected > 0:
            self.items[self.selected-1], self.items[self.selected] = \
            self.items[self.selected], self.items[self.selected-1]
            self.selected -= 1
            self._updatetop()

    def moveitemdown(self):
        "move selected item down, if not last"
        if self.selected is not None and self.selected < len(self)-1:
            self.items[self.selected], self.items[self.selected+1] = \
            self.items[self.selected+1], self.items[self.selected]
            self.selected += 1
            self._updatetop()
