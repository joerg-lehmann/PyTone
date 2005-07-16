##############################################################################
#
# Copyright (c) 2004 TINY SPRL. (http://tiny.be) All Rights Reserved.
#                    Fabien Pinckaers <fp@tiny.Be>
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################
import os.path
import urllib
import md5
import time
import csv

class BadAuthError(Exception):
    pass

class NotConnectedError(Exception):
    pass

class SubmissionError(Exception):
    pass

class Scrobbler(object):

    client = 'tst'
    version = '0.1'
    url = 'http://post.audioscrobbler.com/'
    backlogfile = os.path.expanduser('~/.audioscrobbler')

    def __init__(self, user, password):
        self.user = user
        self.password = password
        self.connected = False
        self.lastconnected = 0

    def dohandshake(self):
        timestamp = str(int(time.time()))
        pswd = md5.new(md5.new(self.password).hexdigest() +
                timestamp).hexdigest()
        rs = urllib.urlencode(
                { 'hs' : 'true',
                  'p' : '1.1',
                  'c' : self.client,
                  'v' : self.version,
                  'u' : self.user,
                  't' : int(time.time()),
                  'a' : pswd })
        url = self.url + "?" + rs
        result = urllib.urlopen(url).readlines()
        if result[0].startswith('UPTODATE'):
            return True, False, result[1:]
        elif result[0].startswith('UPDATE'):
            return True, True, result[1:]
        elif result[0].startswith('FAILED'):
            return False, True, result
        elif result[0].startswith('BADUSER'):
            return False, False, result

    def handshake(self):
        connected = False
        nbtries = 0
        while not connected:
            connected, newclient, results = self.dohandshake()
            if connected:
                self.connected = True
                self.newclient = newclient
                self.md5 = results[0][:-1]
                self.submitURL = results[1][:-1]
                self.lastconnected = time.time()
            else:
                if not newclient:
                    connected = True
                    raise BadAuthError
                time.sleep(2**nbtries * 60)
                nbtries += 1
                if nbtries > 4:
                    connected = True

    def submit(self, song):
        self.sendInfo(song.artist, song.title, song.album, song.length,
                             song.lastplayed[-1])

    def sendInfo(self, artist, title, album, length, debut):
        if self.lastconnected - time.time() > 300:
            self.connected = False
            self.newclient = False
            self.md5 = ''
            self.submitURL = ''
            self.handshake()

        if not self.connected:
            raise NotConnectedError

        pswd = md5.new(md5.new(self.password).hexdigest() +
                self.md5).hexdigest()
        infodict = { 'u' : self.user, 's' : pswd, 'a[0]' : artist,
            't[0]' : title, 'b[0]' : album, 'm[0]' : '', 'l[0]' : length,
            'i[0]' : time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(debut))}
        rs = urllib.urlencode(infodict)

        try:
            result = urllib.urlopen(self.submitURL, rs).readlines()
        except IOError:
            self.addBacklog(infodict)
            return False

        if result[0].startswith('OK'):
            return True
        elif result[0].startswith('FAILED'):
            raise SubmissionError
        elif result[0].startswith('BADAUTH'):
            raise BadAuthError

    def addBacklog(self, info):
        fd = file(self.backlogfile, 'wa')
        writer = csv.writer(fd)
        writer.writerow([info["a[0]"], info["t[0]"], info["b[0]"], info["l[0]"],
                info["i[0]"]])
        fd.close()

    def getBacklog(self):
        try:
            reader = csv.reader(file(self.backlogfile, 'r'))
        except IOError:
            return
        backlogs = list(reader)
        file(self.backlogfile, 'w').close()
        for entry in backlogs:
            self.sendInfo(*entry)
            time.sleep(1)

def main():
    class A:
        pass
    a = A()
    a.artist = raw_input('Artiste: ')
    a.title = raw_input('Titre: ')
    a.album = raw_input('Album: ')
    a.length = raw_input('Duree: ')
    a.lastplayed = [ int(time.time() - 250) ]

    scrobbler = Scrobbler('user', '*****')
    scrobbler.handshake()
    scrobbler.submit(a)

if __name__ == '__main__':
    main()
