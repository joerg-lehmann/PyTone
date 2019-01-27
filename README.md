
PyTone
======

Music Jukebox Redux
-------------------

Summary
-------

PyTone is a music jukebox written in Python with a curses based GUI. While
providing advanced features like crossfading and multiple players, special
emphasis is put on ease of use, turning PyTone into an ideal jukebox system for
use at parties.

Features
--------

* simple song selection
  + using an arbitrary number of music databases with hierarchical
    (artist/album/songs, some tags/artist/album/songs) navigation,
  + from list of top and last played songs,
  + from list of most recently added songs,
  + random song list,
  + stored playlists, or
  + alternatively from file system
* editable playlist:
  + deletion
  + move song up/down
  + delete played songs
  + shuffle
  + repetition and automatic addition of random songs, when the 
    playlist is empty
  + save to and load from .m3u file
* pluggable players, currently
  + internal MP3/Ogg Vorbis player with crossfading and/or
  + xmms based external player and/or
  + mpg321 or (the non-free) mpg123 based external player
* display of information for currently selected song:
  + ID3 tag
  + length, bitrate, sample rate, BPM, ReplayGain information, part
    of a compilation, podcast
  + times played and skipped
  + last played
  + song rating (1 to 5 stars)
* plays currently selected song on second player (if your computer
  has a second sound card or one card with more than one line out)
* search functionality:
  + quick search by first letter
  + incremental search by regular expression
* random song selection taking into account song rating and time at
  which song was last played
* description of important key bindings in status bar and context 
  sensitive help
* random song suggestion
* logging of played songs
* execution of arbitrary command when playback of new song starts
* basic mixer functionality
* customizable key bindings
* customizable look
* English, French, German, Italian and Polish user interface
* external control, e.g. from the shell
* plugin system; currently plugins for the AudioScrobbler service and
  for displaying the title in the terminal window and using xosd are
  included

Software prerequisites
----------------------

* Python 3.5 (available from [here][1]),
* mutagen (available from [here][2]),
* for the mad based internal player (optional):
  + Python header files,
  + pymad (available from [here][3]) and
  + pyvorbis (optional, available from [here][4]),
  + pyao 1.2 and above (available from [here][5]) or 
    the new Python OSS module (on supported systems).
  + libao header files (available from [here][6], if you want to compile
    the C version of the output ring-buffer.
* for the mpg321 or mpg123 based external player (optional):
  + mpg321 (available from [here][7]) or
  + mpg123 (available from [here][8])

oad

   The latest version of PyTone can be downloaded as gzipped tar archive
   from [here][9].

Installation
------------

If you want to use the internal libmad based player, you have to build
one C extension module located in the pcm subdirectory. This
can be done simply via

   $ python setup.py build_ext -i

Note that you can also build a C extension module for the output
ring-buffer, which requires the libao header files (see above) by setting
"buildbufferedaoext = True" at the top of the setup.py file before running the
above command.

Configuration
-------------

   All configuration options of PyTone can be found in the sample configuration
   file conf/pytonerc. Side-wide configuration goes into /etc/pytonerc, user
   specific changes can be put into ~/.pytone/pytonerc. Note that you only have
   to supply options you want to change. Note that you only have to supply
   options you want to change. Furthermore, while most of the standard settings
   will probably fit your needs, you have to change the variable musicbasedir
   in the section [database.main] of the main database, which specifies the
   root of your primary MP3 collection. A minimal version of your configuration
   file should thus contain

     # minimal ~/.pytone/pytonerc defining the root of your music collection
     [database.main]
     musicbasedir=/root/of/your/music/collection

Usage
-----

After having adjusted the basic configuration variables to your personal
needs, just start the program with

   $ ./pytone

and look how the database is being rebuilt. The key bindings described
below should say all about the use of PyTone. A list of command line
options can be obtained by

   $ ./pytone --help

Then let it rock...

The remote control of PyTone is possible using the  pytonectl script.
For a list of available options use:

   $ ./pytonectl --help

In order for the remote control to work, either the socketfile or the
enableserver option have to be set in the [network] section of the pytonerc
file. By default, the former is the case.

Key bindings
------------

   In database/filelist window (left half of screen)

   ArrowUp                      move selection up
   ArrowDown                    move selection down
   PageUp/CTRL-P                move selection one page up
   PageDown/CTRL-N              move selection one page down
   Home/CTRL-A                  move selection to beginning
   End/CTRL-E                   move selection to end
   ArrowRight/Enter/Space       enter directory / add song
   ArrowLeft                    exit directory
   i/ALT+ArrowRight             add song or directory (recursively)
   r                            insert random selection of selected directory
                                (including subdirs)
   u                            update ID3 information for song/directory
   D                            delete / undelete currently selected
                                song/directory
   ALT+Enter                    immediately play song
   TAB                          switch to playlist window
   ALT+<character>              Quicksearch: jump to next entry that begins
                                with character
   CTRL-S//                     Search in list
   f                            Focus on songs matching approximately a search
                                string

   In playlist window (lower right quarter half of screen)

   ArrowUp                      move selection up
   ArrowDown                    move selection down
   PageUp/CTRL-P                move selection one page up
   PageDown/CTRL-N              move selection one page down
   Home/CTRL-A                  move selection to beginning
   End/CTRL-E                   move selection to end
   +                            move selected song up
   -                            move selected song down
   d                            delete selected song
   ALT+Enter                    immediately play song
   r                            shuffle playlist
   TAB/ArrowLeft/h              switch to database/filelist window
   ArrowRight/l                 jump to currently selected song in filelist window

   Always active

   p                            start/pause playing
   S                            stop playing
   n                            advance to next song in playlist
   b                            go back to previous song in playlist
   >                            fast forward in song
   <                            rewind in song
   BACKSPACE                    delete played songs
   CTRL-D                       clear playlist
   CTRL-W                       save playlist to file
   CTRL-R                       load playlist from file
   (                            decrease output volume
   )                            increase output volume
   {                            decrease playback speed
   }                            increase playback speed
   ~                            reset playback speed to normal
   1 - 5                        change rating of selected item
   ALT-1 - ALT-5                change rating of currently playing song
   ?                            show help
   !                            show message log
   %                            show statistical information about database(s)
   =                            show information about selected item
   L                            show lyrics of selected song
   CTRL-V                       toggle information shown in item info window
   F10                          toggle UI layout (one/two column)
   CTRL-X CTRL-X                exit program (the keypresses have to be 
                                maximally one tenth of a second apart)


Mailing list
------------

   For discussions on PyTone, a mailing list has been created. For more
   information on subscribing and for the list archive, see [here][10].

History
-------

   PyTone was written since my favourite MP3 Jukebox (KJukebox) wasn't
   maintained anymore. Its simple user interface and good usability even
   without a mouse combined with the crossfading ability of the player,
   have not been reached by any other free program. Especially for the
   use at a party, KJukebox was very well suited.

   a curses based MP3 Jukebox system, which featured a really simple and
   efficient GUI. Unfortunately, it was written in C and already the
   first attempts to tailor it to my needs showed that probably a Python
   version of this program would be a great win. That's how the
   development of PyTone started...

   After one week of intensive programming version 1.0 of what was then
   called pyjuke was ready and was deployed during a three day long
   party. It proved to be very usable (even on a 38400 baud serial
   terminal) and astoundingly stable, even under extreme, Woodstock like
   conditions (very heavy rain + deep mud :-) )

   Subsequently, the internal mad based player was written, which
   provides crossfading capabilities without using xmms, a new, more
   imaginative name was found (kudos to Harry!) and PyTone was released.


Copyright and author
--------------------

PyTone was written by Jörg Lehmann and is free software licensed under
the GNU GPL Version 2.

Please send comments, wishes, bug reports and patches to the
[mailing list][10]or directly to me, 

  Jörg Lehmann <joerg@luga.de>

Of course, I always like to hear of happy users of PyTone.

Links
-----

[1]: http://www.python.org/
[2]: https://mutagen.readthedocs.org/
[3]: http://spacepants.org/src/pymad/
[4]: http://ekyo.nerim.net/software/pyogg/index.html
[5]: https://github.com/tynn/PyAO
[6]: http://www.xiph.org/ao/
[7]: http://mpg321.sourceforge.net/
[8]: http://www.mpg123.de/
[9]: http://www.luga.de/pytone/PyTone-latest.tar.gz
[10]: https://www.luga.de/mailman/listinfo/pytone-users/
[11]: http://mjs.sourceforge.net/
