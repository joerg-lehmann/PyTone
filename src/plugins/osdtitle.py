### OSD title plugin for pytone
### """""""""""""""""""""""""""
### This plugin displays on-screen song titles whenever pytone changes to
### a new song. You can install this plugin by simply copying it to your
### pytone system-wide plugin directory (eg. /usr/share/pytone/plugins
### or ~/pytone/plugins/). And enable it by adding it to the plugins list
### in the general section, like:
###
###     [general]
###     plugins = osdtitle
###
### You can customise the title by adding the following to /etc/pytonerc
### or ~/.pytone/pytonerc
###
###     [plugin.osdtitle]
###     songformat = %(artist)s - %(title)s (%(length)s)
###     font = -adobe-helvetica-bold-r-*-*-*-240-*-*-*-*-*-*
###     color = green
###     position = top
###     offset = 60
###     align = center
###     shadow = 2
###     lines = 1
###
### See the osd_cat(1) manpage for more information about these options.
###
### You can find the latest release at:
###
###     http://dag.wieers.com/home-made/pytone/
###
### If you have improvements or changes to this plugin, please
### send them to the pytone mailinglist and include me as well:
###
###     pytone-users@luga.de, Dag Wieers <dag@wieers.com>

import events, plugin, config, os, re

class config(config.configsection):
    songformat = config.configstring('%(artist)s - %(title)s (%(length)s)')
    font = config.configstring('-adobe-helvetica-bold-r-*-*-*-240-*-*-*-*-*-*')
    color = config.configstring('green')
    position = config.configstring('top')
    offset = config.configstring('60')
    align = config.configstring('center')
    shadow = config.configstring('2')
    lines = config.configstring('1')

class plugin(plugin.plugin):
    def init(self):
        self.channel.subscribe(events.playbackinfochanged, self.playbackinfochanged)
        self.command = 'osd_cat -p %(position)s -c %(color)s -o %(offset)s -A %(align)s -s %(shadow)s -l %(lines)s -f %(font)s -' % self.config
        self.previoussong = ''

    def playbackinfochanged(self, event):
        if event.playbackinfo.song != self.previoussong:
            if event.playbackinfo.song:
                song = event.playbackinfo.song.format(self.config.songformat, safe=True)
                os.system('echo "%s" | %s &' % (song, self.command))
            self.previoussong = event.playbackinfo.song

# vim:ts=4:sw=4
