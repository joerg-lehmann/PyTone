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

import service
import config

class plugin:

    def __init__(self, channel, config, mainscreen):
        """ create a plugin instance """
        self.channel = channel
        self.config = config
        self.mainscreen = mainscreen

    def start(self):
        self.init()

    def init(self):
        """ initialize plugin after it has been configured """


class threadedplugin(service.service, plugin):

    def __init__(self, channel, config, mainscreen):
        service.service.__init__(self, self.__class__.__name__, daemonize=True)
        # as independent thread, we have to use our own channel which has
        # been created by the service constructor
        plugin.__init__(self, self.channel, config, mainscreen)

    def run(self):
        self.init()
        service.service.run(self)
