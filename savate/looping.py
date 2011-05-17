#! -*- coding: utf-8 -*-

import errno
import select
import logging

try:
    Poller = select.epoll
    POLLIN = select.EPOLLIN
    POLLOUT = select.EPOLLOUT
    POLLERR = select.EPOLLERR
    POLLHUP = select.EPOLLHUP
except NameError:
    Poller = select.poll
    POLLIN = select.POLLIN
    POLLOUT = select.POLLOUT
    POLLERR = select.POLLERR
    POLLHUP = select.POLLHUP

class BaseIOEventHandler(object):

    def close(self):
        self.sock.close()
        self.sock = None

    def fileno(self):
        return self.sock.fileno()

class IOLoop(object):

    DEFAULT_TIMEOUT = 0.5

    def __init__(self, logger = None):
        self.poller = Poller()
        self.handlers = {}
        self.injected_events = {}
        self.logger = logger or logging.getLogger('looping')

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
        fd = io_event_handler.fileno()
        if fd in self.handlers:
            self.poller.unregister(fd)
            del self.handlers[fd]
            self.injected_events.pop(fd, None)

    def once(self, timeout = 0):
        while True:
            try:
                if Poller == select.poll:
                    events_list = self.poller.poll(timeout * 1000)
                else:
                    # We specify maxevents here, since the default -1
                    # means maxevents will be set to FD_SETSIZE - 1,
                    # i.e. 1023, when calling epoll_wait()
                    events_list = self.poller.poll(timeout, len(self.handlers) or -1)
                break
            except IOError, exc:
                if exc.errno == errno.EINTR:
                    continue
                else:
                    raise
        for fd, eventmask in self._merge_eventlists(dict(events_list)).items():
            try:
                handler = self.handlers[fd]
            except KeyError, exc:
                # There's a bug somewhere. Could be epoll, could be us.
                self.logger.error('fd %d returned by epoll() is not in self.handlers !')
                try:
                    self.poller.unregister(fd)
                except:
                    pass
                continue
            try:
                handler.handle_event(eventmask)
            except Exception, exc:
                # We're kinda hardcore
                self.logger.exception('Exception when handling eventmask %s for fd %s:', eventmask, fd)
                self.unregister(handler)
                handler.close()
