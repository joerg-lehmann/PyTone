# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002 Jörg Lehmann <joerg@luga.de>
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

import exceptions

class pytoneerror(exceptions.Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return "PyTone error: %s" % `self.value`

class configurationerror(pytoneerror):
    def __str__(self):
        return "PyTone configuration error: %s" % `self.value`

class databaseerror(pytoneerror):
    def __str__(self):
        return "PyTone database error: %s" % `self.value`
            
class playererror(pytoneerror):
    def __str__(self):
        return "PyTone player error: %s" % `self.value`
