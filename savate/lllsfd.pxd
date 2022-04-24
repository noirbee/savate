cdef extern from 'time.h':

        ctypedef long time_t

        # Used to export constants in the .pyx file
        cdef int _CLOCK_MONOTONIC "CLOCK_MONOTONIC"
        cdef int _CLOCK_REALTIME "CLOCK_REALTIME"
        cdef int _TFD_NONBLOCK "TFD_NONBLOCK"
        cdef int _TFD_CLOEXEC "TFD_CLOEXEC"
        cdef int _TFD_TIMER_ABSTIME "TFD_TIMER_ABSTIME"

        struct timespec:
                time_t tv_sec
                long tv_nsec

        struct itimerspec:
                timespec it_interval
                timespec it_value

cdef extern from 'sys/timerfd.h':

        int timerfd_create(int clockid, int flags) nogil
        int timerfd_settime(int fd, int flags, itimerspec *new_value, itimerspec *old_value) nogil
        int timerfd_gettime(int fd, itimerspec *curr_value) nogil
