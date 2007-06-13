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

import os.path, re, struct, string, time
import encoding
import log

# artist name for compilations
VARIOUS = u"___VARIOUS___"

tracknrandtitlere = re.compile("^\[?(\d+)\]? ?[- ] ?(.*)\.(mp3|ogg)$")

##############################################################################
# song metadata class
##############################################################################

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

##############################################################################
# registry for metadata decoders for various fileformats
##############################################################################

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
# registry for metadata postprocessors for metadata
##############################################################################

_metadata_postprocessors = {}
# mapping: metadata postprocessor name -> metadata postprocessing function

def register_metadata_postprocessor(name, metadata_postprocessor):
    """ register a metadata postprocessor function of the given name

    - The name must not contain any whitespace 
    - metadata_postprocessor has to be a callable accepting exactly one
      parameter which will be an instance of the metadata class. 
    """
    _metadata_postprocessors[name] = metadata_postprocessor

def get_metadata_postprocessor(name):
    return _metadata_postprocessors[name]

##############################################################################
# factory function for song metadata
##############################################################################

def metadata_from_file(relpath, basedir, tracknrandtitlere, postprocessors):
    """ create song metadata from given file with relative (to basedir) path 
    relpath applying the given list of postprocessors"""

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

    # strip leading and trailing whitespace
    if md.title:
        md.title = md.title.strip()
    if md.artist:
        md.artist = md.artist.strip()
    if md.album:
        md.album = md.album.strip()

    if md.length is None:
        log.warning("could not read length of song %r" % path)
        raise RuntimeError("could not read length of song %r" % path)

    for postprocessor_name in postprocessors:
        try:
            get_metadata_postprocessor(postprocessor_name)(md)
        except:
            log.warning("Postprocessing of song %r metadata with '%r' failed" % (path, postprocessor_name))
            log.debug_traceback()

    # set album_artist if not present
    if md.album_artist is None:
        if md.compilation: 
            md.album_artist = VARIOUS
        else:
            md.album_artist = md.artist

    return md

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


# accent_trans = string.maketrans('ÁÀÄÂÉÈËÊÍÌÏÎÓÒÖÔÚÙÜÛáàäâéèëêíìïîóòöôúùüû',
#                                'AAAAEEEEIIIIOOOOUUUUaaaaeeeeiiiioooouuuu')

##############################################################################
# ID3 metadata decoder (using mutagen module)
##############################################################################

def _splitnumbertotal(s):
    """ split string into number and total number """
    r = map(int, s.split("/"))
    number = r[0]
    if len(r) == 2:
        count = r[1]
    else:
        count = None
    return number, count

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
    log.info("MP3 support enabled: using mutagen module for id3 tag parsing")
except ImportError:
    try:
        import eyeD3
        registerfileformat("mp3", read_mp3_eyeD3_metadata, ".mp3")
        log.info("MP3 support enabled: using eyeD3 module for id3 tag parsing")
    except ImportError:
        log.info("MP3 support disabled: no metadata reader module found")


##############################################################################
# Ogg Vorbis metadata decoder
##############################################################################

def read_vorbis_metadata(md, path):
    vf = ogg.vorbis.VorbisFile(path)

    # We use the information for all streams (not stream 0).
    # XXX Is this correct?
    md.length = int(vf.time_total(-1))
    md.bitrate = vf.bitrate(-1)

    md.samplerate = vf.info().rate
    md.is_vbr = vf.info().bitrate_lower != vf.info().bitrate_upper

    for name, value in vf.comment().as_dict().items():
        value = value[0]
        if name == "TITLE": md.title = value
        if name == "ALBUM": md.album = value
        if name == "ARTIST": md.artist = value
        if name == "DATE": 
            try: md.year = int(value)
            except ValueError: pass
        if name == "GENRE" and value:
            md.tags.append("G:%s" % value)
        if name == "COMMENT":
           md.comments = [value]
        if name == "TRACKNUMBER":
            try: md.tracknumber = int(value)
            except ValueError: pass
        if name == "TRACKCOUNT":
            try: md.trackcount = int(value)
            except ValueError: pass
        if name == "DISCNUMBER":
            try: md.disknumber = int(value)
            except ValueError: pass
        if name == "DISCCOUNT":
            try: md.diskcount = int(value)
            except ValueError: pass
        if name == "BPM":
            try: md.bpm = int(value)
            except ValueError: pass
        if name.startswith("REPLAYGAIN_"):
            # ReplayGain:
            # example format according to vorbisgain documentation
            # REPLAYGAIN_TRACK_GAIN=-7.03 dB
            # REPLAYGAIN_TRACK_PEAK=1.21822226
            # REPLAYGAIN_ALBUM_GAIN=-6.37 dB
            # REPLAYGAIN_ALBUM_PEAK=1.21822226
            try:
                profile, type = name[11:].split("_")
                basename = "replaygain_%s_" % profile.tolower()
                if type == "GAIN":
                   md[basename + "gain"] = float(value.split()[0])
                   if not md.has_key(basename + "peak" % profile):
                        md[basename + "peak"] = 1.0
                if type == "PEAK":
                   md[basename + "peak"] = float(value)
                   if not md.has_key(basename + "gain"):
                        md[basename + "gain"] = 0.0
            except (ValueError, IndexError):
                pass

        # XXX how is the song lyrics stored?
        # md.lyrics = []

try:
    import ogg.vorbis
    registerfileformat("ogg", read_vorbis_metadata, ".ogg")
    log.info("Ogg Vorbis support enabled")
except ImportError:
    log.info("Ogg Vorbis support disabled: ogg.vorbis module not found")


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
    log.info("FLAC support enabled (VERY EXPERIMENTAL)")
except ImportError:
    log.info("FLAC support disabled: flac module not found")

##############################################################################
# various metadata postprocessors
##############################################################################

def md_pp_capitalize(md):
    def capwords(s):
        # capitalize words also directly after a single punctuation character
        words = []
        for word in s.split():
            if word[0] in string.punctuation:
                words.append(word[0] + word[1:].capitalize())
            else:
                words.append(word.capitalize())
        return " ".join(words)

    if md.title:
        md.title = capwords(md.title)
    if md.artist:
        md.artist = capwords(md.artist)
    if md.album:
        md.album = capwords(md.album)

def md_pp_strip_leading_article(md):
    # strip leading "The " in artist names, often used inconsistently
    if md.artist and md.artist.startswith("The ") and len(md.artist)>4:
        md.artist = md.artist[4:]

def md_pp_remove_accents(md):
    # XXX disabled because I don't know how to get translate working
    # with unicode strings (except for encoding them first)
    md.artist = md.artist.translate(accent_trans)
    md.album = md.album.translate(accent_trans)
    md.title = md.title.translate(accent_trans)

def md_pp_add_decade_tag(md):
    # automatically add decade tag
    if md.year:
        md.tags.append("D:%d" % (10*(md.year//10)))

register_metadata_postprocessor("capitalize", md_pp_capitalize)
register_metadata_postprocessor("strip_leading_article", md_pp_strip_leading_article)
register_metadata_postprocessor("add_decade_tag", md_pp_add_decade_tag)

#    if "Compilations" in relpath:
#       md.compilation = True
