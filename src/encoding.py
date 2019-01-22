import sys
import locale

_localecharset = locale.getpreferredencoding()

_fs_encoding = sys.getfilesystemencoding()
#if _fs_encoding in [None, 'ascii', 'ANSI_X3.4-1968']:


# exported functions

def encode(ustring):
    return ustring.encode(_localecharset, "replace")

def decode(string):
    return string.decode(_localecharset, "replace")

def encode_path(path):
    return path.encode(_fs_encoding)
