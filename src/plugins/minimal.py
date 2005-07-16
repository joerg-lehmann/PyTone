# -*- coding: ISO-8859-1 -*-

import events
import plugin
import config
import log
import copy

# We define a config section, which will be called [plugin.minimal]
# In the plugin, we will be able to access the values as member variable
# self.config

class config(config.configsection):
    message = config.configstring("new song: ")

class plugin(plugin.plugin):

    """ a simple plugin that logs when a new song is played on the main player

    A configuration option message allows the user to specify the notification string.
    """

    def start(self):
        # its good practice to notify the user of the started plugin
        log.info("started minimal plugin")
        self.playbackinfo = None
        self.channel.subscribe(events.playbackinfochanged, self.playbackinfochanged)

    # event handler

    def playbackinfochanged(self, event):
        if event.playbackinfo is None:
            return
        if self.playbackinfo is None or self.playbackinfo.song != event.playbackinfo.song:
            log.info("%s%s" % (self.config.message, event.playbackinfo.song))
            self.playbackinfo = copy.copy(event.playbackinfo)

