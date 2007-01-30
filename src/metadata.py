# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2005, 2006 Jörg Lehmann <joerg@luga.de>
#
# Ogg Vorbis interface by Byron Ellacott <bje@apnic.net>.
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

import os.path, re, struct, time
import encoding
import log

# artist name for compilations
VARIOUS = u"___VARIOUS___"

tracknrandtitlere = re.compile("^\[?(\d+)\]? ?[- ] ?(.*)\.(mp3|ogg)$")

#
# song metadata class
#

class song_metadata:

    url = None
    type = None
    title = None
    album = None
    artist = None
    album_artist = None
    tags = None
    year = None
    comments = []       # list of tuples (language, description, text)
    lyrics = []         # list of tuples (language, description, text)
    bpm = None
    tracknumber = None
    trackcount = None
    disknumber = None
    diskcount = None
    compilation = False
    length = None
    size = None
    bitrate = None
    is_vbr = None
    samplerate = None
    rating = None
    replaygain_track_gain = None
    replaygain_track_peak = None
    replaygain_album_gain = None
    replaygain_album_peak = None
    date_added = None
    date_updated = None
    dates_played = []
    # the following two items are redundant but stored for efficieny reasons
    date_lastplayed = None
    playcount = 0                 # times fully played
    skipcount = 0                 # times skipped

    def __init__(self):
        self.tags = []
        self.date_updated = self.date_added = time.time()

    def __repr__(self):
        return "metadata(%r)" % (self.url)

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        return setattr(self, key, value)

    def update(self, other):
        " merge filesystem metadata from other into self "
        assert other.url == self.url, RuntimeError("song urls changed")
        self.title = other.title
        self.album = other.album
        self.artist = other.artist
        self.album_artist = other.album_artist
        # keep user tags
        usertags = [tag for tag in self.tags if tag[:2] == "U:"]
        self.tags = other.tags + usertags
        self.year = other.year
        self.comments = other.comments
        self.lyrics = other.lyrics
        self.bpm = other.bpm
        self.tracknumber = other.tracknumber
        self.trackcount = other.trackcount
        self.disknumber = other.disknumber
        self.diskcount = other.diskcount
        self.compilation = other.compilation
        self.length = other.length
        self.size = other.size
        self.bitrate = other.bitrate
        self.is_vbr = other.is_vbr
        self.samplerate = other.samplerate
        self.replaygain_track_gain = other.replaygain_track_gain
        self.replaygain_track_peak = other.replaygain_track_peak
        self.replaygain_album_gain = other.replaygain_album_gain
        self.replaygain_album_peak = other.replaygain_album_peak
        self.date_updated = other.date_updated

#
# factory function for song metadata
#

def metadata_from_file(relpath, basedir, 
                       tracknrandtitlere, capitalize, stripleadingarticle, removeaccents):
    """ create song metadata from given file with relative (to basedir) path relpath """

    path = os.path.normpath(os.path.join(basedir, relpath))
    if not os.access(path, os.R_OK):
        raise IOError("cannot read song")

    md = song_metadata()
    md.size = os.stat(path).st_size
    md.type = gettype(os.path.splitext(path)[1])

    read_path_metadata(md, relpath, tracknrandtitlere)

    try:
        metadatadecoder = getmetadatadecoder(md.type)
    except:
        raise RuntimeError("Support for %s songs not enabled" % md.type)

    try:
        log.debug("reading metadata for %r" % path)
        metadatadecoder(md, path)
        log.debug("metadata for %r read successfully" % path)
    except:
        log.warning("could not read metadata for %r" % path)
        log.debug_traceback()

    regularize_metadata(md, capitalize, stripleadingarticle, removeaccents)

    if md.length is None:
        log.warning("could not read length of song %r" % path)
        raise RuntimeError("could not read length of song %s" % path)

    # automatically add tags
    if md.year:
        md.tags.append("D:%d" % (10*(md.year//10)))

    return md

#
# various helper functions for different sub tasks 
#

def read_path_metadata(md, relpath, tracknrandtitlere):
    relpath = os.path.normpath(relpath)

    md.url = u"file://" + encoding.decode_path(relpath)

    # guesses for title and tracknumber using the filename
    match = re.match(tracknrandtitlere, os.path.basename(relpath))
    if match:
        fntracknumber = int(match.group(1))
        fntitle = match.group(2)
    else:
        fntracknumber = None
        fntitle = os.path.basename(relpath)
        if fntitle.lower().endswith(".mp3") or fntitle.lower().endswith(".ogg"):
            fntitle = fntitle[:-4]

    first, second = os.path.split(os.path.dirname(relpath))
    if first and second and not os.path.split(first)[0]:
        fnartist = first
        fnalbum = second
    else:
        fnartist = fnalbum = ""

    # now convert this to unicode strings using the standard filesystem encoding
    fntitle = encoding.decode_path(fntitle)
    fnartist = encoding.decode_path(fnartist)
    fnalbum = encoding.decode_path(fnalbum)

    fntitle = fntitle.replace("_", " ")
    fnalbum = fnalbum.replace("_", " ")
    fnartist = fnartist.replace("_", " ")

    if fntitle:
        md.title = fntitle
    if fnartist:
        md.artist = fnartist
    if fnalbum:
        md.album = fnalbum
    if fntracknumber:
        md.tracknumber = fntracknumber

    if "Compilations" in relpath:
        md.compilation = True

# accent_trans = string.maketrans('ÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛáàäâéèëêíìïîóòöôúùüû',
#                                'AAAAEEEEIIIIOOOOUUUUaaaaeeeeiiiioooouuuu')

def regularize_metadata(md, capitalize, stripleadingarticle, removeaccents):
    if md.title:
        md.title = md.title.strip()
    if md.artist:
        md.artist = md.artist.strip()
    if md.album:
        md.album = md.album.strip()

    if capitalize:
        if md.title:
            md.title = string.capwords(md.title)
        if md.artist:
           md.artist = string.capwords(md.artist)
        if md.album:
            mdalbum = string.capwords(md.album)

    if stripleadingarticle and md.artist:
        # strip leading "The " in artist names, often used inconsistently
        if md.artist.startswith("The ") and len(md.artist)>4:
            md.artist = md.artist[4:]

    # XXX disabled because I don't know how to get translate working
    # with unicode strings (except for encoding them first)
    if removeaccents and 0:
        md.artist = md.artist.translate(accent_trans)
        md.album = md.album.translate(accent_trans)
        md.title = md.title.translate(accent_trans)

    if md.album_artist is None:
        if md.compilation: 
            md.album_artist = VARIOUS
        else:
            md.album_artist = md.artist


#
# various metadata readers for different file formats
#

# mapping: file type -> (metadata, decoder class, file extension)
_fileformats = {}

def registerfileformat(type, metadataclass, extension):
    _fileformats[type] = (metadataclass, extension)

def getmetadatadecoder(type):
    return _fileformats[type][0]

def getextensions():
    result = []
    for decoder_function, extension in _fileformats.values():
        result.append(extension)
    return result

def gettype(extension):
    for type, extensions in _fileformats.items():
        if extension.lower() in extensions:
            return type
    return None


##############################################################################
# ID3 metadata decoder (using mutagen module)
##############################################################################

_mutagen_framemapping = { "TIT2": "title",
                          "TALB": "album",
                          "TPE1": "artist" }

def read_mp3_mutagen_metadata(md, path):

    mp3 = mutagen.mp3.MP3(path, ID3=ID3hack)

    # we definitely want the MP3 header data, even if no ID3 tag is present,
    # so extract this info before anything goes wrong
    md.length = mp3.info.length
    md.samplerate = mp3.info.sample_rate
    md.bitrate = mp3.info.bitrate
    md.comments = []
    md.lyrics = []

    if mp3.tags:
        for frame in mp3.tags.values():
            if frame.FrameID == "TCON":
                genre = " ".join(frame.genres)
                if genre:
                    md.tags.append("G:%s" % genre)
            elif frame.FrameID == "RVA2":
                if frame.channel == 1:
                    if frame.desc == "album":
                        basename = "replaygain_album_"
                    else:
                        # for everything else, we assume it's track gain
                        basename = "replaygain_track_"
                    md[basename+"gain"] = frame.gain
                    md[basename+"peak"] = frame.peak
            elif frame.FrameID == "TLEN":
                try:
                    # we overwrite the length which maybe has been defined above
                    md.length = int(+frame/1000)
                except:
                    pass
            elif frame.FrameID == "TRCK":
                md.tracknumber, md.trackcount = _splitnumbertotal(frame.text[0])
            elif frame.FrameID == "TPOS":
                md.disknumber, md.diskcount = _splitnumbertotal(frame.text[0])
            elif frame.FrameID == "TBPM":
                md.bpm = int(+frame)
            #elif frame.FrameID == "TCMP":
            #   self.compilation = True
            elif frame.FrameID == "TDRC":
                try:
                    md.year = int(str(frame.text[0]))
                except:
                    pass
            elif frame.FrameID == "USLT":
                md.lyrics.append((frame.lang, frame.desc, frame.text))
            elif frame.FrameID == "COMM":
                md.comments.append((frame.lang, frame.desc, " / ".join(frame.text)))
            else:
                name = _mutagen_framemapping.get(frame.FrameID, None)
                if name:
                    text = " ".join(map(unicode, frame.text))
                    md[name] = text
    else:
        log.debug("Could not read ID3 tags for song '%r'" % path)


##############################################################################
# ID3 metadata decoder (using eyeD3 module)
##############################################################################

def read_mp3_eyeD3_metadata(md, path):
    mp3file = eyeD3.Mp3AudioFile(path)
    mp3info = mp3file.getTag()

    # we definitely want the length of the MP3 file, even if no ID3 tag is present,
    # so extract this info before anything goes wrong
    md.length = mp3file.getPlayTime()

    md.is_vbr, bitrate = mp3file.getBitRate()
    md.bitrate = bitrate * 1000
    md.samplerate = mp3file.getSampleFreq()
    md.comments = []
    md.lyrics = []

    if mp3info:
        md.title = mp3info.getTitle()
        md.album = mp3info.getAlbum()
        md.artist = mp3info.getArtist()
        try:
            md.year = int(mp3info.getYear())
        except:
            pass
        try:
            genre = mp3info.getGenre()
        except eyeD3.tag.GenreException, e:
            genre = e.msg.split(':')[1].strip()
        if genre:
            md.tags.append("G:%s" % genre)

        md.tracknumber, md.trackcount = mp3info.getTrackNum()
        md.disknumber, md.diskcount = mp3info.getDiscNum()

        # if the playtime is also in the ID3 tag information, we
        # try to read it from there
        if mp3info.frames["TLEN"]:
            length = None
            try:
                length = int(int(mp3info.frames["TLEN"])/1000)
            except:
                # time in seconds (?), possibly with bad decimal separator, e.g "186,333"
                try:
                    length = int(float(mp3info.frames["TLEN"].replace(",", ".")))
                except:
                    pass
            if length:
                md.length = length
        md.lyrics = u"".join(mp3info.getLyrics())
        md.comments = u"".join(mp3info.getComments())
        md.bpm = mp3info.getBPM()

        for rva2frame in mp3info.frames["RVA2"]:
            # since eyeD3 currently doesn't support RVA2 frames, we have to decode
            # them on our own following mutagen
            desc, rest = rva2frame.data.split("\x00", 1)
            channel = ord(rest[0])
            if channel == 1:
                gain = struct.unpack('>h', rest[1:3])[0]/512.0
                # http://bugs.xmms.org/attachment.cgi?id=113&action=view
                rest = rest[3:]
                peak = 0
                bits = ord(rest[0])
                bytes = min(4, (bits + 7) >> 3)
                shift = ((8 - (bits & 7)) & 7) + (4 - bytes) * 8
                for i in range(1, bytes+1):
                    peak *= 256
                    peak += ord(rest[i])
                peak *= 2**shift
                peak = (float(peak) / (2**31-1))
                if desc == "album":
                    basename = "replaygain_album_"
                else:
                    # for everything else, we assume it's track gain
                    basename = "replaygain_track_"
                md[basename+"gain"] = gain
                md[basename+"peak"] = peak

try:
    import mutagen.mp3
    import mutagen.id3

    # copied from quodlibet
    class ID3hack(mutagen.id3.ID3):
        "Override 'correct' behavior with desired behavior"
        def loaded_frame(self, tag):
            if len(type(tag).__name__) == 3: tag = type(tag).__base__(tag)
            if tag.HashKey in self and tag.FrameID[0] == "T":
                self[tag.HashKey].extend(tag[:])
            else: self[tag.HashKey] = tag

    registerfileformat("mp3", read_mp3_mutagen_metadata, ".mp3")
    log.info("using mutagen module for id3 tag parsing")
except ImportError:
    try:
        import eyeD3
        registerfileformat("mp3", read_mp3_eyeD3_metadata, ".mp3")
        log.info("using eyeD3 module for id3 tag parsing")
    except ImportError:
        log.info("MP3 support disabled, since no metadata reader module has been found")


##############################################################################
# Ogg Vorbis metadata decoder
##############################################################################

def read_vorbis_metadata(md, path):
    vf = ogg.vorbis.VorbisFile(path)


    id3get = vf.comment().as_dict().get
    md.title = id3get('TITLE', [""])[0]
    md.album = id3get('ALBUM', [""])[0]
    md.artist = id3get('ARTIST', [""])[0]
    md.year = int(id3get('DATE', [""])[0])
    genre  = id3get('GENRE', [""])[0]
    if genre:
        md.tags.append("G:%s" % genre)
    md.length = int(vf.time_total(0))

    # XXX to be implemented
    # md.samplerate =
    # md.bitrate =
    # md.comments = []
    # md.lyrics = []
    # md.tracknumber, md.trackcount =
    # md.disknumber, md.diskcount =
    # md.bpm =

    # example format according to vorbisgain documentation
    # REPLAYGAIN_TRACK_GAIN=-7.03 dB
    # REPLAYGAIN_TRACK_PEAK=1.21822226
    # REPLAYGAIN_ALBUM_GAIN=-6.37 dB
    # REPLAYGAIN_ALBUM_PEAK=1.21822226

try:
    import ogg.vorbis
    registerfileformat("ogg", read_vorbis_metadata, ".ogg")
    log.info("Ogg Vorbis support enabled")
except ImportError:
    log.info("Ogg Vorbis support disabled, since ogg.vorbis module is not present")

def _splitnumbertotal(s):
    """ split string into number and total number """
    r = map(int, s.split("/"))
    number = r[0]
    if len(r) == 2:
        count = r[1]
    else:
        count = None
    return number, count


##############################################################################
# FLAC metadata decoder
##############################################################################

def read_flac_metadata(md, path):
    chain = flac.metadata.Chain()
    chain.read(path)
    it = flac.metadata.Iterator()
    it.init(chain)
    while 1:
        block = it.get_block()
        if block.type == flac.metadata.VORBIS_COMMENT:
            comment = flac.metadata.VorbisComment(block).comments
            id3get = lambda key, default: getattr(comment, key, default)
            self.title = id3get('TITLE', "")
            self.album = id3get('ALBUM', "")
            self.artist = id3get('ARTIST', "")
            self.year = id3get('DATE', "")
            self.genre  = id3get('GENRE', "")
            self.tracknr = id3get('TRACKNUMBER', "")
        elif block.type == flac.metadata.STREAMINFO:
            streaminfo = block.data.stream_info
            self.length = streaminfo.total_samples / streaminfo.sample_rate
        if not it.next():
            break

try:
    import flac.metadata
    registerfileformat("flac", read_flac_metadata, ".flac")
    log.info("flac support enabled (VERY EXPERIMENTAL)")
except ImportError:
    log.info("flac support disabled, since flac module is not present")
