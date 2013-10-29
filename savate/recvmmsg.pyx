# -*- coding: utf-8 -*-

from cpython.mem cimport PyMem_Malloc, PyMem_Free
from cpython.buffer cimport PyObject_GetBuffer, PyBuffer_Release, PyBUF_WRITABLE
from libc.string cimport memset

cdef extern from 'errno.h':

        cdef int errno

import os

from recvmmsg cimport recvmmsg as _recvmmsg


def recvmmsg(int fd, object buffers, int flags = 0):
    cdef iovec *iovectors
    cdef mmsghdr *messages_vectors
    cdef Py_buffer *py_buffers

    ret_buffers = buffers

    cdef int buffer_number = len(buffers)

    try:
        iovectors = <iovec *> PyMem_Malloc(buffer_number * sizeof(iovec))
        messages_vectors = <mmsghdr *> PyMem_Malloc(buffer_number * sizeof(mmsghdr))
        py_buffers = <Py_buffer *> PyMem_Malloc(buffer_number * sizeof(Py_buffer))

        if not iovectors or not messages_vectors or not py_buffers:
            raise MemoryError

        memset(iovectors, 0, buffer_number * sizeof(iovec))
        memset(messages_vectors, 0, buffer_number * sizeof(mmsghdr))
        memset(py_buffers, 0, buffer_number * sizeof(Py_buffer))

        for i in range(buffer_number):
            if PyObject_GetBuffer(buffers[i], &(py_buffers[i]), PyBUF_WRITABLE) != 0:
                raise BufferError('Supplied buffer does not support writing')
            messages_vectors[i].msg_hdr.msg_iov = &iovectors[i]
            messages_vectors[i].msg_hdr.msg_iov[0].iov_base = py_buffers[i].buf
            messages_vectors[i].msg_hdr.msg_iov[0].iov_len = py_buffers[i].len
            messages_vectors[i].msg_hdr.msg_iovlen = 1

            # We must set these to zero since we don't support them
            messages_vectors[i].msg_hdr.msg_name = NULL
            messages_vectors[i].msg_hdr.msg_control = NULL
            messages_vectors[i].msg_hdr.msg_flags = 0

        with nogil:
            recv_messages = _recvmmsg(fd, messages_vectors, buffer_number, flags, NULL)

        if recv_messages == -1:
            global errno
            raise IOError(errno, os.strerror(errno))

        for i in range(recv_messages):
            message_length = messages_vectors[i].msg_len
            if message_length != len(ret_buffers[i]):
                ret_buffers[i] = ret_buffers[i][:message_length]

        return ret_buffers[:recv_messages]

    finally:
        for i in range(buffer_number):
            PyBuffer_Release(&(py_buffers[i]))
        PyMem_Free(iovectors)
        PyMem_Free(messages_vectors)
        PyMem_Free(py_buffers)
