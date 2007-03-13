### Terminal title plugin for pytone
### """"""""""""""""""""""""""""""""
### This plugin updates terminal and screen titles whenever pytone
### changes to a new song. You can install this plugin by simply
### copying it to your pytone system-wide plugin directory 
### (eg. /usr/share/pytone/plugins or ~/pytone/plugins/). And
### enable it by adding it to the plugins list in the general
### section, like:
###
###     [general]
###     plugins = termtitle
###
### You can customise the title by adding the following to
### /etc/pytonerc or ~/.pytone/pytonerc
###
###     [plugin.termtitle]
###     songformat = pytone: %(title)s - %(artist)s - %(length)s
###
### You can find the latest release at:
###
###     http://dag.wieers.com/home-made/pytone/
###
### If you have improvements or changes to this plugin, please
### send them to the pytone mailinglist and include me as well:
###
###     pytone-users@luga.de, Dag Wieers <dag@wieers.com>

import events, encoding, plugin, config, sys, os, re

class config(config.configsection):
    songformat = config.configstring('%(artist)s - %(title)s (%(length)s)')

class plugin(plugin.plugin):
    def init(self):
        if re.compile('(screen|xterm*)').match(os.getenv('TERM')):
            self.channel.subscribe(events.playbackinfochanged, self.playbackinfochanged)
            self.previoussong = None
            self.previouscross = False
        else:
            raise RuntimeError("Terminal type not supported")

    def playbackinfochanged(self, event):
        if event.playbackinfo.song and event.playbackinfo.song != self.previoussong or event.playbackinfo.iscrossfading() != self.previouscross:
            self.changetermtitle(event)
            self.previoussong = event.playbackinfo.song
            self.previouscross = event.playbackinfo.iscrossfading()

    def changetermtitle(self, event):
        prefix = (event.playbackinfo.iscrossfading() and '-> ' or '')
        song = encoding.encode(event.playbackinfo.song.format(self.config.songformat, safe=True))
        sys.stdout.write('\033]0;' + prefix + song + '\007')

# vim:ts=4:sw=4
