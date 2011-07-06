# -*- coding: utf-8 -*-

from savate.looping import BaseIOEventHandler, POLLIN
from savate.lllsfd import TimerFD, CLOCK_REALTIME, TFD_TIMER_ABSTIME


class Timeouts(BaseIOEventHandler):

    def __init__(self, server):
        BaseIOEventHandler.__init__(self)
        self.server = server
        self.timer = self.sock = TimerFD(clockid = CLOCK_REALTIME)
        # A timestamp -> {handlers} dict
        self.timeouts = {}
        # A handler -> timestamp dict
        self.handlers_timeouts = {}

    def min_expiration(self):
        return sorted(self.timeouts.keys())[0]

    def update_timeout(self, handler, expiration):
        if (not self.timeouts) or (expiration < self.min_expiration()):
            # Specified expiration is earlier that our current one,
            # update our timer
            self.timer.settime(expiration, flags = TFD_TIMER_ABSTIME)

        # Do we need to update an existing timeout ?
        if handler.sock in self.handlers_timeouts:
            old_expiration = self.handlers_timeouts[handler.sock]
            self.timeouts[old_expiration].pop(handler.sock)
        self.handlers_timeouts[handler.sock] = expiration
        self.timeouts.setdefault(expiration, {})[handler.sock] = handler

    def remove_timeout(self, handler):
        if handler.sock in self.handlers_timeouts:
            expiration = self.handlers_timeouts.pop(handler.sock)
            self.timeouts.get(expiration, {}).pop(handler.sock, None)

    def handle_event(self, eventmask):
        if eventmask & POLLIN:
            # Seems we need to "flush" the FD's expiration counter to
            # avoid some strange poll-ability bugs
            self.timer.read()
            # Timer expired
            timed_out_handlers = self.timeouts.pop(self.min_expiration())
            for handler in timed_out_handlers.values():
                self.server.logger.error('Timeout for %s: %d seconds without I/O' %
                                         (handler, self.server.INACTIVITY_TIMEOUT))
                self.handlers_timeouts.pop(handler.sock)
                handler.close()
            if self.timeouts:
                # Reset the timer to the earliest one
                self.timer.settime(self.min_expiration(), flags = TFD_TIMER_ABSTIME)
        else:
            self.server.logger.error('%s: unexpected eventmask %d (%s)', self, eventmask, event_mask_str(eventmask))
