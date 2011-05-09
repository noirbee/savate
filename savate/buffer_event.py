# -*- coding: utf-8 -*-

import errno
import collections
from savate import writev

# FIXME: should this be a method of BufferEvent below ?
# FIXME: handle Python2.x/Python3k compat here
def buffer_slice(buff, offset, size):
    return buffer(buff, offset, size)

class BufferOutputHandler(object):

    def __init__(self, sock, initial_buffer_queue = ()):
        self.sock = sock
        self.ready = True
        self.buffer_queue = collections.deque(initial_buffer_queue)

    def add_buffer(self, buff):
        self.buffer_queue.append(buff)

    def empty(self):
        return len(self.buffer_queue) == 0

    def flush(self):
        self.ready = True
        total_sent_bytes = 0
        try:
            while self.buffer_queue:
                sent_bytes = writev.writev(self.sock.fileno(),
                                             self.buffer_queue)
                total_sent_bytes += sent_bytes
                while (self.buffer_queue and sent_bytes and
                       len(self.buffer_queue[0]) <= sent_bytes):
                    sent_bytes -= len(self.buffer_queue.popleft())
                if sent_bytes:
                    # One of the buffers was partially sent
                    self.buffer_queue[0] = self.buffer_queue[0][sent_bytes:]
        except IOError, exc:
            if exc.errno == errno.EAGAIN:
                self.ready = False
            else:
                raise
        return total_sent_bytes
