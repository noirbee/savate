# -*- coding: utf-8 -*-

cdef extern from 'sys/uio.h':

        struct iovec:
                void *iov_base
                size_t iov_len

        ssize_t writev(int fd, iovec *iov, int iovcnt) nogil

cdef extern from 'limits.h':

        # Dummy anonymous enum to emulate an external #define
        cdef enum:
                IOV_MAX
