import time
import errno
import select
import logging
import socket
from abc import ABC, abstractmethod
from typing import Literal, Optional


try:
    Poller = select.epoll
    POLLIN = select.EPOLLIN
    POLLOUT = select.EPOLLOUT
    POLLERR = select.EPOLLERR
    POLLHUP = select.EPOLLHUP
except (AttributeError, NameError):
    Poller = select.poll  # type: ignore[misc, assignment]
    POLLIN = select.POLLIN
    POLLOUT = select.POLLOUT
    POLLERR = select.POLLERR
    POLLHUP = select.POLLHUP


class BaseIOEventHandler(ABC):

    sock: socket.socket

    def close(self) -> None:
        self.sock.close()
        del self.sock
        # self.sock = None

    def fileno(self) -> int:
        return self.sock.fileno()

    @abstractmethod
    def handle_event(self, eventmask: int) -> None:
        ...


class IOLoop:

    DEFAULT_TIMEOUT = 0.5

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.poller = Poller()
        self.handlers: dict[int, BaseIOEventHandler] = {}
        self.injected_events: dict[int, int] = {}
        self.logger = logger or logging.getLogger('looping')
        self._now = time.time()

    def register(self, io_event_handler: BaseIOEventHandler, eventmask: int) -> None:
        if io_event_handler.fileno() not in self.handlers:
            self.poller.register(io_event_handler.fileno(), eventmask)
        else:
            self.poller.modify(io_event_handler.fileno(), eventmask)
        self.handlers[io_event_handler.fileno()] = io_event_handler

    def inject_event(self, fd: int, eventmask: int) -> None:
        self.injected_events[fd] = self.injected_events.get(fd, 0) | eventmask

    def _merge_eventlists(self, events_list: dict[int, int]) -> dict[int, int]:
        while self.injected_events:
            fd, eventmask = self.injected_events.popitem()
            events_list[fd] = events_list.get(fd, 0) | eventmask
        return events_list

    def unregister(self, io_event_handler: BaseIOEventHandler) -> None:
        try:
            fd = io_event_handler.fileno()
        except IOError as exc:
            # already unregistered
            if exc.errno != errno.EBADF:
                raise
            # FIXME: do we need to handle more exceptions ?
            return

        if fd in self.handlers:
            self.poller.unregister(fd)
            del self.handlers[fd]
            self.injected_events.pop(fd, None)

    def now(self) -> float:
        return self._now

    def once(self, timeout: float = 0) -> None:
        while True:
            try:
                if Poller == select.poll:  # type: ignore[comparison-overlap]
                    events_list = self.poller.poll(timeout * 1000)
                else:
                    # We specify maxevents here, since the default -1
                    # means maxevents will be set to FD_SETSIZE - 1,
                    # i.e. 1023, when calling epoll_wait()
                    events_list = self.poller.poll(timeout, len(self.handlers) or -1)
                break
            except IOError as exc:
                if exc.errno == errno.EINTR:
                    continue
                else:
                    raise

        # Update our idea of the current time
        self._now = time.time()

        for fd, eventmask in list(self._merge_eventlists(dict(events_list)).items()):
            try:
                handler = self.handlers[fd]
            except KeyError as exc:
                # There's a bug somewhere. Could be epoll, could be us.
                self.logger.error('fd %d returned by epoll() is not in self.handlers !', fd)
                try:
                    self.poller.unregister(fd)
                except:
                    pass
                continue
            try:
                handler.handle_event(eventmask)
            except Exception as exc:
                # We're kinda hardcore
                self.logger.exception('Exception when handling eventmask %s for fd %s:', eventmask, fd)
                self.unregister(handler)
                handler.close()
