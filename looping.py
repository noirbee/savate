#! -*- coding: utf-8 -*-

import errno
import select
import traceback

POLLIN = select.EPOLLIN
POLLOUT = select.EPOLLOUT
POLLET = select.EPOLLET

class BaseIOEventHandler(object):

    def close(self):
        self.sock.close()
        self.sock = None

    def fileno(self):
        return self.sock.fileno()

class IOLoop(object):

    DEFAULT_TIMEOUT = 0.5

    def __init__(self):
        self.poller = select.epoll()
        self.handlers = {}
        self.injected_events = {}

    def register(self, io_event_handler, eventmask):
        if io_event_handler.fileno() not in self.handlers:
            self.poller.register(io_event_handler.fileno(), eventmask)
        else:
            self.poller.modify(io_event_handler.fileno(), eventmask)
        self.handlers[io_event_handler.fileno()] = io_event_handler

    def inject_event(self, fd, eventmask):
        self.injected_events[fd] = self.injected_events.get(fd, 0) | eventmask

    def _merge_eventlists(self, events_list):
        while self.injected_events:
            fd, eventmask = self.injected_events.popitem()
            events_list[fd] = events_list.get(fd, 0) | eventmask
        return events_list

    def unregister(self, io_event_handler):
        # FIXME: this may need some exception handling
        if io_event_handler.fileno() in self.handlers:
            self.poller.unregister(io_event_handler.fileno())
            del self.handlers[io_event_handler.fileno()]

    def once(self, timeout = 0):
        while True:
            try:
                events_list = self.poller.poll(timeout)
                break
            except IOError, exc:
                if exc.errno == errno.EINTR:
                    continue
                else:
                    raise
        for fd, eventmask in self._merge_eventlists(dict(events_list)).items():
            handler = self.handlers[fd]
            try:
                handler.handle_event(eventmask)
            except Exception, exc:
                # We're kinda hardcore
                traceback.print_exc()
                self.unregister(handler)
                handler.close()
