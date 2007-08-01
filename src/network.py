# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2003 Jörg Lehmann <joerg@luga.de>
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

import SocketServer, socket
import threading, tempfile, time, os.path
import cPickle, cStringIO
import events, hub
import log

# for unpickling
import item, metadata, requests, services, services.player, services.playlist, copy_reg, __builtin__

_EVENT = "EVENT"
_REQUEST = "REQUEST"
_RESULT = "RESULT"
_SUBSCRIBE = "SUBSCRIBE"
_SENDFILE = "SENDFILE"

##############################################################################
# restricted unpickling
##############################################################################


def find_global(module, klass):
    if module in ("events", "requests", "metadata", "copy_reg", "__builtin__"):
        pass
    elif module=="item" and klass=="song":
        pass
    elif module=="dbitem":
        pass
    elif module=="services.player":
        pass
    elif module=="services.playlist":
        pass
    else:
        log.debug("refusing to unpickle %s.%s" % (module, klass))
        raise cPickle.UnpicklingError, \
              "cannot unpickle a %s.%s" % (module, klass)
    log.debug("unpickling %s.%s" % (module, klass))
    return eval("%s.%s" % (module, klass))

def loads(s):
    unpickler = cPickle.Unpickler(cStringIO.StringIO(s))
    unpickler.find_global = find_global
    return unpickler.load()


##############################################################################
# server part
##############################################################################

class servernetworkreceiver(threading.Thread):
    """ helper thread that processes requests coming from clients

    We need this, since there is no select which accepts both a socket and
    a queue.

    """

    def __init__(self, socket, handler):
	self.socket = socket
	self.handler = handler
	self.rfile = self.socket.makefile("r")
	self.done = False
	threading.Thread.__init__(self)
	self.setDaemon(1)

    def _receiveobject(self):
	line = self.rfile.readline()
        if not line: return None, None
	try:
            log.debug("server: request type received")
	    type, bytes = line.split()
	    bytes = int(bytes)
	    if type != _SENDFILE:
 		objstring = self.rfile.read(bytes+2)[:-2]
                log.debug("server: object received")
                obj = loads(objstring)
                log.debug("server receive: type=%s object=%s" % (type, `obj`))
		return (type, obj)
	    else:
		# we handle send file requests separately
		filename = self.rfile.readline()
		tmpfilename = tempfile.mktemp()
		bytes = bytes-len(filename)-2
		tmpfile = open(tmpfilename, "w")
		while bytes>2:
		    rbytes = min(bytes, 4096)
		    tmpfile.write(self.rfile.read(rbytes))
		    bytes -= rbytes
		self.rfile.read(2)
		return (type, tmpfilename)
	except Exception, e:
            log.debug("exception '%s' occured during _receiveobject" % e)
	    return (None, None)

    def run(self):
        # process events, request and subscription requests coming from
        # the client
	while not self.done:
	    type, obj = self._receiveobject()
	    if type == _EVENT:
                log.debug("server: client sends event '%s'" % obj)
		hub.notify(obj, priority=-50)
	    elif type == _REQUEST:
                log.debug("server: requesting %s for client" % `obj`)
		# extract id
		rid, obj = obj
		result = hub.request(obj, priority=-50)
		log.debug("server: got answer %s" % `result`)
		# be careful, handler may not exist anymore?
		try:
		    self.handler._sendobject(_RESULT, (rid, result))
		except:
		    pass
	    elif type == _SUBSCRIBE:
		log.debug("server: client requests subscription for '%s'" % `obj`)
		# be careful, maybe handler does not exists anymore?
		try:
		    self.handler.subscribe(obj)
		except:
		    pass
	    else:
                log.debug("server: servernetworkreceiver exits: type=%s" % type)
		self.done = True
		self.handler.done = True


class handler(SocketServer.StreamRequestHandler, SocketServer.BaseRequestHandler):
    """ handles requests by clients """
    rbufsize = 0

    def _sendobject(self, type, obj):
	# we have to switch to blocking mode for send
	# self.request.setblocking(1)
	objstring = cPickle.dumps(obj, 1)
	self.wfile.write("%s %d\r\n%s\r\n" % (type, len(objstring), objstring))
	self.wfile.flush()
	log.debug("server send: type=%s object=%s" % (type, `obj`))

    def handle(self):
        log.debug("starting handler")
	self.channel = hub.newchannel()
	self.done = False
	self.servernetworkreceiver = servernetworkreceiver(self.request, self)
	self.servernetworkreceiver.start()

        # Process events coming from the rest of the PyTone server.
        # This sends (via eventhandler) subscribed events to the client
	while not self.done:
	    self.channel.process(block=True)
	log.debug("terminating handler")
	self.channel.hub.disconnect(self.channel)

    def subscribe(self, event):
        # clientnetworkreceiver calls this method to subscribe to certain events
	self.channel.subscribe(event, self.eventhandler)

    #
    # event handler
    #

    def eventhandler(self, event):
        # send every subscribed event to client
	log.debug("network event handler called")
	self._sendobject(_EVENT, event)

# boilerplate server code

class tcpserver(threading.Thread):
    allow_reuse_address = 1
    def __init__(self, bind, port):
        self.bind = bind
	self.port = port
	threading.Thread.__init__(self)
	self.setDaemon(1)

    def run(self):
	while 1:
	    try:
		self.tcpserver = SocketServer.ThreadingTCPServer((self.bind, self.port), handler)
		break
	    except:
		log.debug("server thread is waiting for port to become free")
		time.sleep(1)
	self.tcpserver.serve_forever()

class unixserver(threading.Thread):
    def __init__(self, filename):
	self.filename = filename
        try:
            os.unlink(self.filename)
        except OSError, e:
            if e.errno!=2:
                raise
	threading.Thread.__init__(self)
	self.setDaemon(1)

    def run(self):
        self.unixserver = SocketServer.ThreadingUnixStreamServer(self.filename, handler)
	self.unixserver.serve_forever()

##############################################################################
# client part
##############################################################################

class clientnetworkreceiver(threading.Thread):
    """ helper thread that receives from socket and puts result in queue

    We need this, since there is no select which accepts both a socket and
    a queue.

    """

    def __init__(self, socket, queue):
	self.socket = socket
	self.rfile = self.socket.makefile("r")
	self.queue = queue
	self.done = False
	threading.Thread.__init__(self)
	self.setDaemon(1)

    def _receiveobject(self):
	try:
	    line = self.rfile.readline()
	    type, bytes = line.split()
	    bytes = int(bytes)
	    objstring = self.rfile.read(bytes+2)[:-2]
	    log.debug("client receive: %s bytes" % len(objstring))
	    obj = loads(objstring)
	    log.debug("client receive: type=%s object=%s" % (type, repr(obj)))
	    return (type, obj)
	except:
	    return (None, None)

    def run(self):
	while not self.done:
	    self.queue.put((self._receiveobject(), 100))

#
# bidirectional (sending + receiving) client functionality is provided by the clientchannel
# and its subclasses
#

class clientchannel(threading.Thread):
    def __init__(self, networklocation):
        # network location is either a tuple (server adress, port) or a
        # filename pointing to a socket file
        try:
            server, port = networklocation
            family = socket.AF_INET
        except ValueError:
            filename = networklocation
            family = socket.AF_UNIX
            
        self.socket = socket.socket(family, socket.SOCK_STREAM)
        if family == socket.AF_INET:
            self.socket.connect((server, port))
        else:
            self.socket.connect(filename)

	self.subscriptions = []
	self.wfile = self.socket.makefile("wb")
	self.queue = hub.PriorityQueue(-1)
	self.clientnetworkreceiver = clientnetworkreceiver(self.socket, self.queue)
	self.clientnetworkreceiver.start()
	# hash for pending requests
	self.pendingrequests = {}
	self.done = False
	threading.Thread.__init__(self)
	self.setDaemon(1)
        log.debug("Network clientchannel initialized")

    def _sendobject(self, type, obj):
        log.debug("client send: type=%s object=%s" % (type, obj))
        try:
            objstring = cPickle.dumps(obj, cPickle.HIGHEST_PROTOCOL)
        except Exception, e:
            log.debug_traceback()
	self.wfile.write("%s %d\r\n%s\r\n" % (type, len(objstring), objstring))
	self.wfile.flush()

    def sendfile(self, filename):
	basename = os.path.basename(filename)
	file = open(filename, "r")
	f.seek(0, 2)
	filelen = f.tell()
	f.seek(0, 0)
	# length of request
	rlen = len(basename) + 2 + filelen
	self.wfile.write("%s %d\r\n%s\r\n" % (_SENDFILE, rlen, basename))
	while filelen>0:
	    wbytes = min(filelen, 4096)
	    self.wfile.write(file.read(wbytes))
	    filelen -= wbytes
	self.wfile.write("\r\n")
	self.wfile.flush()
	log.debug("client send: type=%s object=file:%s" % (type, filename))

    def subscribe(self, eventtype, handler):
	# Note that the subscription semantics is a little bit different compared
	# with that of hub.py. The clientchannel is a thread of its own, so
	# it calls the playback without being in a process method!
	self._sendobject(_SUBSCRIBE, eventtype)
	self.subscriptions.append((eventtype, handler))

    def run(self):
	while not self.done:
	    item = self.queue.get()
	    if isinstance(item, events.event):
                self._sendobject(_EVENT, item)
	    elif isinstance(item, hub.requestresponse):
		# send request including id
		rid = id(item)
                log.debug("Sending request (id=%d)" % rid)
		self._sendobject(_REQUEST, (rid, item.request))
		self.pendingrequests[rid] = item
	    else: # input from networkreceiver: tuple (type, obj)
		type, obj = item
		if type==_EVENT:
                    log.debug("Received event from networkreceiver")
		    try:
			for subscribedevent, handler in self.subscriptions:
			    if isinstance(obj, subscribedevent):
				handler(obj)
		    except TerminateEventProcessing:
			pass
		elif type==_RESULT:
		    rid, obj = obj
                    log.debug("Received request result (id=%d) from networkreceiver" % rid)
		    item = self.pendingrequests[rid]
		    item.result = obj
		    item.ready.set()
		    del self.pendingrequests[rid]

    def notify(self, item, priority=0):
	""" notify channel of item (event or request) """
	self.queue.put((item, -priority))

    def request(self, request, priority=0):
	""" submit a request (blocking)

	this method submits a request, waits for the result and
	returns it.  Requests with a high priority are treated first.
	"""
	# generate a request response object for the request,
	# send it to hub and wait for result
	rr = hub.requestresponse(request)
	self.notify(rr, priority)
	rr.waitforcompletion()
	return rr.result

    def quit(self):
        while not self.queue.empty():
            time.sleep(0.1)
        self.done = True
        
#
# unidirectional (only sending) client functionality is provided by the sender
# and its subclasses
#

class sender:
    def __init__(self, socket):
        self.socket = socket
	self.wfile = self.socket.makefile("wb")
        log.debug("Network sender initialized")
    
    def sendevent(self, event):
	objstring = cPickle.dumps(event, 1)
	self.wfile.write("%s %d\r\n%s\r\n" % (_EVENT, len(objstring), objstring))
	self.wfile.flush()

    def close(self):
        self.socket.close()


class tcpsender(sender):
    def __init__(self, server, port):
	asocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	asocket.connect((server, port))
        sender.__init__(self, asocket)


class unixsender(sender):
    def __init__(self, filename):
        asocket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
	asocket.connect(filename)
        sender.__init__(self, asocket)
