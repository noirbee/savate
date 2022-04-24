import errno
import collections
import socket
from typing import Sequence


class QueueSizeExceeded(Exception):
    pass


class BufferOutputHandler:

    # FIXME: make this configurable
    MAX_QUEUE_SIZE = 24 * 2**20

    def __init__(self, sock: socket.socket, initial_buffer_queue: Sequence[bytes] = ()) -> None:
        self.sock = sock
        self.ready = True
        self.buffer_queue = collections.deque(memoryview(buff) for buff in initial_buffer_queue)

    def add_buffer(self, buff: bytes) -> None:
        self.buffer_queue.append(memoryview(buff))

    def empty(self) -> bool:
        return len(self.buffer_queue) == 0

    def queue_size(self) -> int:
        return sum(len(buf) for buf in self.buffer_queue)

    def flush(self) -> int:
        self.ready = True
        total_sent_bytes = 0
        try:
            while self.buffer_queue:
                sent_bytes = self.sock.send(self.buffer_queue[0])
                total_sent_bytes += sent_bytes
                if sent_bytes < len(self.buffer_queue[0]):
                    # One of the buffers was partially sent
                    self.buffer_queue[0] = self.buffer_queue[0][sent_bytes:]
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
            raise QueueSizeExceeded("%d > %d" % (self.queue_size(), self.MAX_QUEUE_SIZE))
        return total_sent_bytes
