#!/usr/bin/python

import hotshot

def main():
    import pytone

prof = hotshot.Profile("PyTone.prof")
prof.runcall(main)
prof.close()
