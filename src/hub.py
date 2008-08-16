# -*- coding: ISO-8859-1 -*-

# Copyright (C) 2003, 2004 Jörg Lehmann <joerg@luga.de>
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

import exceptions
import threading
import Queue

import events, log

class TerminateEventProcessing(exceptions.Exception):
    pass

class DenyRequest(exceptions.Exception):
    """ deny processing of a request """
    pass

# from http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/87369

class PriorityQueue(Queue.Queue):

    def _init(self, maxsize):
        # we need to be sure to have a list as underlying queue
        self.maxsize = maxsize
        self.queue = []
        
    def _put(self, item):
	data, priority = item
	self._insort_right((priority, data))

    def _get(self):
	return self.queue.pop(0)[1]

    def _insort_right(self, x):
	"""Insert item x in list, and keep it sorted assuming a is sorted.

	If x is already in list, insert it to the right of the rightmost x.
	"""
	a = self.queue
	lo = 0
	hi = len(a)

	while lo < hi:
	    mid = (lo+hi)/2
	    if x[0] < a[mid][0]: hi = mid
	    else: lo = mid+1
	a.insert(lo, x)

#
# request response class
#

class requestresponse:
    """ structure containing request + response upon request """
    def __init__(self, request):
	self.request = request
	self.result = None
	self.ready = threading.Event()

    def __repr__(self):
	return "requestresponse(%r -> %r)" % (self.request, self.result)

    def waitforcompletion(self):
	self.ready.wait()

    def hascompleted(self):
	return self.ready.isSet()

#
# event and request dispatcher classes
#

class hub:

    """ collects event channels from different threads """

    def __init__(self):
	self.channels = []

    def connect(self, channel):
	self.channels.append(channel)

    def disconnect(self, channel):
	self.channels.remove(channel)

    def newchannel(self):
	achannel = channel(self)
	self.connect(achannel)
	return achannel

    def notify(self, item, priority=0):
	""" notify all channels belonging to hub of item (event or request) """
	log.debug("event: %s (priority %d)" % (repr(item), priority))
	for channel in self.channels:
	    channel._notify(item, priority)

    def request(self, request, priority=0):
	""" submit a request (blocking)

	this method submits a request, waits for the result and
	returns it.  Requests with a high priority are treated first.
	"""
	# generate a request response object for the request,
	# send it to hub and wait for result
	log.debug("request: %s (priority %d)" % (repr(request), priority))
	rr = requestresponse(request)
	self.notify(rr, priority)
	rr.waitforcompletion()
	return rr.result

#    def requestnoblocking(self, request, priority=0):
#        """ submit a request (nonblocking)
#
#        this method submits a request and returns a requestresponse
#        structure.  Requests with a high priority are treated first.
#        """
#        rr = requestresponse(request)
#        self.notify(rr, priority)
#        return rr


class channel:

    """ collects event handlers for one thread """

    def __init__(self, hub):
	self.hub = hub
	self.subscriptions = []
	self.suppliers = []
	self.queue = PriorityQueue(-1)
	# self.queue = Queue.Queue(-1)

    def process(self, block=False, timeout=None):
	""" process queued events and request

	If block is set, we wait for incoming events and requests.  In
        this case, a timeout in seconds can be specified, as well.
	"""

        while True:
            try:
                item = self.queue.get(block=block, timeout=timeout)
            except Queue.Empty:
                break
            # after having get the first event, we do no longer block
            block = False
            timeout = None
	    if isinstance(item, events.event):
		try:
		    for subscribedevent, handler in self.subscriptions:
			if isinstance(item, subscribedevent):
			    handler(item)
		except TerminateEventProcessing:
		    pass
	    else:
		for suppliedrequest, handler in self.suppliers:
		    if isinstance(item.request, suppliedrequest):
			# compute result and signalise that
			# request has been processed
			try:
			    item.result = handler(item.request)
			    log.debug(u"got result for %r" % item.request)
			    r = repr(item.result)
			    log.debug(u"got result %r for %r" % (item.result, item.request))
			    item.ready.set()
			    break
			except DenyRequest:
			    pass

    def subscribe(self, eventtype, handler):
	self.subscriptions.append((eventtype, handler))

    def unsubscribe(self, eventtype, handler):
	self.subscriptions.remove((eventtype, handler))

    def supply(self, requesttype, handler):
	self.suppliers.append((requesttype, handler))

    def unsupply(self, requesttype, handler):
	self.suppliers.remove((requesttype, handler))

    def _notify(self, item, priority=0):
	""" notify channel of item (event or request) """
	self.queue.put((item, -priority))

# set up default hub and provide easy access to its externally used methods
_defaulthub = hub()

newchannel = _defaulthub.newchannel
notify = _defaulthub.notify
request = _defaulthub.request
