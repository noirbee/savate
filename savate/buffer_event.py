# -*- coding: utf-8 -*-

import errno
import collections


# FIXME: should this be a method of BufferEvent below ?
try:
    memoryview
    def make_buffer(data):
        return memoryview(data)
    def buffer_slice(buff, offset):
        return buff[offset:]
except NameError:
    def make_buffer(data):
        return buffer(data)
    def buffer_slice(buff, offset):
        return buffer(buff, offset)


class BufferOutputHandler(object):

    # FIXME: make this configurable
    MAX_QUEUE_SIZE = 24 * 2**20

    def __init__(self, sock, initial_buffer_queue = ()):
        self.sock = sock
        self.ready = True
        self.buffer_queue = collections.deque(make_buffer(buff) for buff in initial_buffer_queue)

    def add_buffer(self, buff):
        self.buffer_queue.append(buff)

    def empty(self):
        return len(self.buffer_queue) == 0

    def queue_size(self):
        return sum(len(buf) for buf in self.buffer_queue)

    def flush(self):
        self.ready = True
        total_sent_bytes = 0
        try:
            while self.buffer_queue:
                sent_bytes = self.sock.send(self.buffer_queue[0])
                total_sent_bytes += sent_bytes
                if sent_bytes < len(self.buffer_queue[0]):
                    # One of the buffers was partially sent
                    self.buffer_queue[0] = buffer_slice(self.buffer_queue[0], sent_bytes)
                    # We assume we can't send any more data
                    self.ready = False
                    break
                else:
                    self.buffer_queue.popleft()
        except IOError as exc:
            if exc.errno == errno.EAGAIN:
                self.ready = False
            else:
                raise
        if self.queue_size() > self.MAX_QUEUE_SIZE:
            raise Exception('Queue size too large for %s: %d', self, self.queue_size())
        return total_sent_bytes
