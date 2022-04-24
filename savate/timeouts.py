import socket
from functools import partial
from typing import TYPE_CHECKING, Any, Callable

from savate.helpers import event_mask_str
from savate.looping import BaseIOEventHandler, POLLIN
from savate.lllsfd import TimerFD, CLOCK_REALTIME, TFD_TIMER_ABSTIME
if TYPE_CHECKING:
    from savate.server import TCPServer


class Timeouts(BaseIOEventHandler):

    def __init__(self, server: "TCPServer") -> None:
        BaseIOEventHandler.__init__(self)
        self.server = server
        self.timer = self.sock = TimerFD(clockid = CLOCK_REALTIME)
        # A timestamp -> {handlers: callbacks} dict
        self.timeouts: dict[float, dict[Any, Callable[..., None]]] = {}
        # A handler -> timestamp dict
        self.handlers_timeouts: dict[Any, float] = {}

    @property
    def min_expiration(self) -> float:
        return min(self.timeouts)

    def reset_timeout(self, key_index: Any, expiration: float, callback: Callable[..., None], *args: Any, **kwargs: Any) -> None:
        """
        :param object key_index: key used in internall dict self.timeouts
        :param numeric expiration: expiration for the given timeout
        :param callable callback: callable called when timeout is fired
        :params *args, **kwargs: optional args for callback
        """
        if (not self.timeouts) or (expiration < self.min_expiration):
            # Specified expiration is earlier that our current one,
            # update our timer
            self.timer.settime(expiration, flags = TFD_TIMER_ABSTIME)

        # Do we need to update an existing timeout ?
        if key_index in self.handlers_timeouts:
            old_expiration = self.handlers_timeouts[key_index]
            self.timeouts[old_expiration].pop(key_index)
        # Construct the callback
        if args or kwargs:  # arguments supplied
            callback = partial(callback, *args, **kwargs)
        self.handlers_timeouts[key_index] = expiration
        self.timeouts.setdefault(expiration, {})[key_index] = callback

    def remove_timeout(self, key_index: Any) -> None:
        """
        :param object key_index: same as self.reset_timeout
        """
        if key_index in self.handlers_timeouts:
            expiration = self.handlers_timeouts.pop(key_index)
            self.timeouts.get(expiration, {}).pop(key_index, None)

    def handle_event(self, eventmask: int) -> None:
        if eventmask & POLLIN:
            # Seems we need to "flush" the FD's expiration counter to
            # avoid some strange poll-ability bugs
            self.timer.read()
            # Timer expired
            expiration = self.min_expiration

            # We use this instead of iterating on
            # self.timeouts[expiration] because closing one of the
            # handlers may close other handlers, and thus remove some
            # of timeouts we're processing in this call (i.e. when a
            # source times out any of its clients that was marked as
            # timed out will be dropped, and removed from the timeouts
            # list)
            while self.timeouts[expiration]:
                key_index, callback = self.timeouts[expiration].popitem()
                self.handlers_timeouts.pop(key_index)
                callback()
            del self.timeouts[expiration]
            if self.timeouts:
                # Reset the timer to the earliest one
                self.timer.settime(self.min_expiration, flags = TFD_TIMER_ABSTIME)
        else:
            self.server.logger.error('%s: unexpected eventmask %d (%s)', self, eventmask, event_mask_str(eventmask))


class IOTimeout:
    """Handles I/O timeouts for a given handler.

    It uses sockets as key_index which permits to share timeout between a Relay
    and its Source.
    """

    def __init__(self, timeout_handler: Timeouts) -> None:
        self.server = timeout_handler.server
        self.timeout_handler = timeout_handler

    def reset_timeout(self, handler: BaseIOEventHandler, expiration: float) -> None:
        self.timeout_handler.reset_timeout(handler.sock, expiration,
                                           self.fired_timeout, handler)

    def remove_timeout(self, handler: BaseIOEventHandler) -> None:
        self.timeout_handler.remove_timeout(handler.sock)

    def fired_timeout(self, handler: BaseIOEventHandler) -> None:
        self.server.logger.error('Timeout for %s: %d seconds without I/O' %
                                 (handler, self.server.INACTIVITY_TIMEOUT))
        handler.close()
