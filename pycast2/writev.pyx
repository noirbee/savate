# -*- coding: utf-8 -*-

import os
import errno as errno_module

cdef extern from 'errno.h':

        int errno

from writev cimport writev as _writev

def writev(int fd, buffer_list):
    cdef iovec buffers[IOV_MAX]
    cdef int i = 0

    if len(buffer_list) > IOV_MAX:
        raise IOError(errno_module.EINVAL, 'Too many buffers (max %d)' % IOV_MAX)

    for buff in buffer_list:
        # FIXME: using a buffer object breaks Cython's <char *> cast
        # (on Python2.6 at least). Find a way to work around this
        # (direct use of the CPython PyBuffer API maybe ?)
        buffers[i].iov_base = <char *>buff
        buffers[i].iov_len = len(buff)
        i += 1
    cdef ssize_t ret = 0
    with nogil:
        ret = _writev(fd, buffers, i)
    if ret < 0:
        global errno
        raise IOError(errno, os.strerror(errno))
    return ret
