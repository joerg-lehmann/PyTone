import locale

_localecharset = locale.getpreferredencoding()

def encode(string):
    return string.encode(_localecharset, "replace")

def decode(_bytes):
    return _bytes.decode(_localecharset, "replace")
