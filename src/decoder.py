# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2002, 2003, 2004, 2005 Jörg Lehmann <joerg@luga.de>

# Ogg Vorbis decoder interface by Byron Ellacott <bje@apnic.net>.
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

import log
import pcm

#
# decoder class and simple decoder registry
#

class decoder:
    def __init__(self, path):
        pass

    def samplerate(self):
        """ return samplerate in samples per second """
        pass

    def ttime(self):
        """ return total length of song in seconds """
        pass

    def ptime(self):
        """ return the current position in the song in seconds """
        pass

    def read(self):
        """ return pcm stream (16bit, 2 channels) """
        pass

    def seekrelative(self, seconds):
        """ seek in stream by the given number of seconds (relative to current position) """
        pass


# mapping: file type -> decoder class
_decoders = {}

def registerdecoder(type, decoderclass):
    _decoders[type] = decoderclass

def getdecoder(type):
    return _decoders[type]

#
# MP3 decoder using libmad
#

class mp3decoder(decoder):
    def __init__(self, path):
        self.file = mad.MadFile(path)

    def samplerate(self):
        return self.file.samplerate()

    def ttime(self):
        return self.file.total_time()//1000

    def ptime(self):
        return self.file.current_time()//1000

    def read(self):
        return self.file.read()

    def seekrelative(self, seconds):
        time = min(max(self.file.current_time() + seconds*1000, 0), self.file.total_time())
        self.file.seek_time(time)

try:
    import mad
    registerdecoder("mp3", mp3decoder)
except ImportError:
    pass

#
# Ogg Vorbis decoder
#

class oggvorbisdecoder(decoder):
    def __init__(self, path):
        self.file = ogg.vorbis.VorbisFile(path)

    def samplerate(self):
        return self.file.info().rate

    def ttime(self):
        return self.file.time_total(0)

    def ptime(self):
        return self.file.time_tell()

    def read(self):
        buff, bytes, bit = self.file.read()
        if self.file.info().channels == 2:
            return buffer(buff, 0, bytes)
        else:
            # for mono files, libvorbis really returns a mono stream
            # (as opposed to libmad) so that we have to "double" the
            # stream before we return it
            return pcm.upsample(buffer(buff, 0, bytes))

    def seekrelative(self, seconds):
        time = min(max(self.file.time_tell() + seconds, 0), self.file.time_total(0))
        self.file.time_seek(time)


try:
    import ogg.vorbis
    registerdecoder("ogg", oggvorbisdecoder)
except ImportError:
    pass

#
# FLAC decoder
#

class flacdecoder(decoder):
    def __init__(self, path):
        self.filedecoder = flac.decoder.FileDecoder()
        self.filedecoder.set_filename(path)
        # register callbacks
        self.filedecoder.set_write_callback(self._write_callback)
        self.filedecoder.set_error_callback(self._error_callback)
        self.filedecoder.set_metadata_callback(self._metadata_callback)
        # init decoder and process (here: ignore) metadata
        self.filedecoder.init()
        self.filedecoder.process_until_end_of_metadata()

        self._ptime = 0  # position in file in seconds

        # to be able to return the sample rate, we have to decode
        # some data
        self.buff = None
        self.filedecoder.process_single()

    def _metadata_callback(self, dec, block):
        if block.type == flac.metadata.STREAMINFO:
            streaminfo = block.data.stream_info
            self._samplerate = streaminfo.sample_rate
            self._channels = streaminfo.channels
            self._bits_per_sample = streaminfo.bits_per_sample
            self._ttime = streaminfo.total_samples // self._samplerate

    def _error_callback(self, dec, block):
        pass

    def _write_callback(self, dec, buff, size):
        self.buff = buff

    def samplerate(self):
        return self._samplerate

    def ttime(self):
        return self._ttime

    def ptime(self):
        return int(self._ptime)

    def read(self):
        if self.buff is None:
            self.filedecoder.process_single()
        if self.buff is not None:
            result = self.buff[:]
            self._ptime += 1.0*len(result)/self._channels/self._bits_per_sample*8/self._samplerate
            # ok, here it becomes very weird. There seems to be a problem with
            # the pyflac module, which does not occur (for me!) when
            # I insert the following code
            try:
                for i in range(100): pass
            except:
                pass
            self.buff = None
            return result

    def seekrelative(self, seconds):
        self._ptime += seconds
        self.filedecoder.seek_absolute(self._ptime * self._samplerate)

try:
    import flac.decoder
    import flac.metadata
    registerdecoder("flac", flacdecoder)
except ImportError:
    pass

#
# main class
#

class decodedsong:

    """ song decoder and rate converter

    This class is for decoding of a song and the conversion of the
    resulting pcm stream to a defined sample rate. Besides the
    constructor, there is only one method, namely read, which
    returns a pcm frame of or less than a given arbitrary size.

    """

    def __init__(self, song, outrate, replaygainprofiles):
        self.song = song
        self.outrate = outrate
        self.default_rate = outrate
        self.replaygain = song.replaygain(replaygainprofiles)

        try:
            decoder = getdecoder(self.song.type)
        except:
            log.error("No decoder for song type '%s' registered "% self.song.type)
            raise RuntimeError("No decoder for song type '%s' registered "% self.song.type)

        self.decodedfile = decoder(song.path)

        # Use the total time given by the decoder library and not the one
        # stored in the database. The former one turns out to be more precise
        # for some VBR songs.
        self.ttime = self.decodedfile.ttime()
        self.samplerate = self.decodedfile.samplerate()

        self.buff = self.last_l = self.last_r = None
        self.buffpos = 0
        self.ptime = 0

    def read(self, size):
        if self.buff is not None:
            bytesleft = len(self.buff) - self.buffpos
        else:
            bytesleft = 0

        # fill buffer, if necessary 
        while bytesleft < size:
            newbuff = self.decodedfile.read()
            if newbuff:
                self.buff, self.last_l, self.last_r = \
                           pcm.rate_convert(newbuff,
                                            self.samplerate,
                                            self.buff,
                                            self.buffpos,
                                            self.outrate,
                                            self.last_l,
                                            self.last_r)

                # the new self.buff contains only new data
                self.buffpos = 0
                bytesleft = len(self.buff)
            else:
                size = bytesleft
                break

        oldpos = self.buffpos
        self.buffpos += size
        self.ptime = self.decodedfile.ptime()
        if self.buff:
            return self.buff[oldpos:self.buffpos]
        else:
            return []

    def seekrelative(self, seconds):
        self.decodedfile.seekrelative(seconds)
        self.buff = self.last_l = self.last_r = None
        self.buffpos = 0
        self.ptime = self.decodedfile.ptime()

    def playslower(self, speed_adj = 441):
        self.outrate += speed_adj

    def playfaster(self, speed_adj = 441):
        # Its absurd that someone would try this
        # but we better check for it.
        if (self.outrate - speed_adj) < 1:
            self.outrate = 1
        else:
            self.outrate -= speed_adj

    def resetplayspeed(self):
        self.outrate = self.default_rate
