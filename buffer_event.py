# -*- coding: utf-8 -*-

import errno
import collections

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
        try:
            while self.buffer_queue:
                tmp_data = self.buffer_queue[0]
                # FIXME: should we use socket.MSG_DONTWAIT here ?
                sent_bytes = self.sock.send(tmp_data)
                tmp_data = buffer_slice(tmp_data, sent_bytes, -1)
                if tmp_data:
                    self.buffer_queue[0] = tmp_data
                else:
                    self.buffer_queue.popleft()
        except IOError, exc:
            if exc.errno == errno.EAGAIN:
                self.ready = False
            else:
                raise
