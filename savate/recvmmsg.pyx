# -*- coding: utf-8 -*-

cdef extern from "Python.h":

        int PyObject_GetBuffer(object obj, Py_buffer *view, int flags)
        void PyBuffer_Release(Py_buffer *view)

        cdef int PyBUF_WRITABLE

cdef extern from 'errno.h':

        cdef int errno

import os
from libc.stdlib cimport malloc, free

from recvmmsg cimport recvmmsg as _recvmmsg


def recvmmsg(int fd, object buffers, int flags = 0):
    cdef iovec *iovectors
    cdef mmsghdr *messages_vectors
    cdef Py_buffer *py_buffers

    ret_buffers = buffers

    buffer_number = len(buffers)

    try:
        iovectors = <iovec *> malloc(buffer_number * sizeof(iovec))
        messages_vectors = <mmsghdr *> malloc(buffer_number * sizeof(mmsghdr))
        py_buffers = <Py_buffer *> malloc(buffer_number * sizeof(Py_buffer))

        if not iovectors or not messages_vectors or not py_buffers:
            raise MemoryError

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

        for i in range(recv_messages):
            message_length = messages_vectors[i].msg_len
            if message_length != len(ret_buffers[i]):
                ret_buffers[i] = ret_buffers[i][:message_length]

        if recv_messages == -1:
            global errno
            raise IOError(errno, os.strerror(errno))

        return ret_buffers[:recv_messages]

    finally:
        for i in range(buffer_number):
            PyBuffer_Release(&(py_buffers[i]))
        free(iovectors)
        free(messages_vectors)
        free(py_buffers)
