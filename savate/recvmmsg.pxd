# -*- coding: utf-8 -*-

cdef extern from 'sys/uio.h':

        struct iovec:
                void *iov_base
                size_t iov_len

cdef extern from 'sys/socket.h':

        ctypedef long time_t
        ctypedef long socklen_t

        # Used to export constants in the .pyx file
        struct msghdr:
                void *msg_name
                socklen_t msg_namelen
                iovec *msg_iov
                size_t msg_iovlen
                void *msg_control
                size_t msg_controllen
                int msg_flags

        struct mmsghdr:
                msghdr msg_hdr
                unsigned int msg_len

        struct timespec:
                time_t tv_sec
                long tv_nsec

        int recvmmsg(int fd, mmsghdr *vmessages, unsigned int vlen, int flags, timespec *tmo) nogil
