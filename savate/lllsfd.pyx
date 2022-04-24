'''
Low-Level Linux Specific File Descriptors module.

Currently supports timerfd.
'''

import os
import fcntl
import struct

from savate cimport lllsfd


cdef extern from 'errno.h':

        cdef int errno


CLOCK_MONOTONIC = lllsfd._CLOCK_MONOTONIC
CLOCK_REALTIME = lllsfd._CLOCK_REALTIME
TFD_NONBLOCK = lllsfd._TFD_NONBLOCK
TFD_CLOEXEC = lllsfd._TFD_CLOEXEC
TFD_TIMER_ABSTIME = lllsfd._TFD_TIMER_ABSTIME


class TimerFD:
    '''
    A low-level interface to Linux' timerfd. Read the
    timerfd_create(2) manual page for a proper description of the
    underlying API / concepts.

    Subsecond precision is not supported as of now.
    '''

    EXPIRATIONS_UNPACKER = struct.Struct('=Q')

    def __init__(self, clockid = CLOCK_MONOTONIC, flags = 0):
        '''
        Creates the timerfd. See the timerfd_create(2) manual page for
        the meaning of the clockid and flags argument.
        '''
        self._fd = lllsfd.timerfd_create(clockid, flags)
        if self._fd == -1:
            global errno
            raise IOError(errno, os.strerror(errno))

    def fileno(self):
        '''
        Returns the underlying timerfd numeric file descriptor.
        '''
        return self._fd

    def gettime(self):
        '''
        Interface to timerfd_gettime(2).

        Returns a tuple (next expiration time, repeat interval), in
        seconds.
        '''
        cdef itimerspec curr_value
        ret = lllsfd.timerfd_gettime(self._fd, &curr_value)
        if ret != 0:
            global errno
            raise IOError(errno, os.strerror(errno))
        return curr_value.it_value.tv_sec, curr_value.it_interval.tv_sec

    def settime(self, expiration, repeat = 0, flags = 0):
        '''
        Interface to timerfd_settime(2).

        Sets the next expiration time and the repeat interval, if
        specified, for the underlying timerfd.

        See the timerfd_settime(2) manual page for the meaning of the
        flags argument.
        '''
        cdef itimerspec new_value

        new_value.it_value.tv_sec = expiration
        new_value.it_value.tv_nsec = 0
        new_value.it_interval.tv_sec = repeat
        new_value.it_interval.tv_nsec = 0

        ret = lllsfd.timerfd_settime(self._fd, flags, &new_value, NULL)
        if ret != 0:
            global errno
            raise IOError(errno, os.strerror(errno))

    def disarm(self):
        '''
        Convenience method to disarm the timer. Equivalent to
        settime(0, 0, 0).
        '''
        return self.settime(0, 0, 0)

    def read(self):
        '''
        Convenience method to get the numver of timer expirations that
        have occurred since the last read().
        '''
        return self.EXPIRATIONS_UNPACKER.unpack(os.read(self._fd, 8))[0]

    def setblocking(self, blocking):
        '''
        Convenience method to set the underlying timerfd FD to
        blocking or nonblocking mode.
        '''
        flags = fcntl.fcntl(self._fd, fcntl.F_GETFL)
        if blocking:
            fcntl.fcntl(self._fd, fcntl.F_SETFL, flags & ~os.O_NONBLOCK)
        else:
            fcntl.fcntl(self._fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def close(self):
        '''
        Closes the underlying timerfd. After this, this TimerFD object
        cannot be used anymore.
        '''
        os.close(self._fd)
