# -*- coding: utf-8 -*-

from struct import Struct

# parsing states
DEF PARSE_HEADER = 0
DEF PARSE_ERROR = 1
DEF MIN_SYNC_FRAMES = 8  # totaly arbitrary, what would be a good number ?


class FrameParsingError(Exception):
    pass


cdef class AbstractAudioParser:

    unpack = Struct('7B').unpack_from

    def __cinit__(self):
        self.parsing_state = PARSE_ERROR
        self.error_back_ref = 1
        self.error_frames = 0
        self.max_frame_length = 8192
        self.lower_bound = 0
        self.upper_bound = 0
        self.buffer_length = 0

    def __init__(self):
        self.buffer = b''
        self.frames = []

        self.error_message = b''

    def feed(self, data):
        self.buffer += data

        self.buffer_length = len(self.buffer)
        self.lower_bound = self.upper_bound = 0

        while True:
            if self.parsing_state == PARSE_HEADER:
                try:
                    if not self.handle_headers():
                        break
                except FrameParsingError as exc:
                    # initialize attributes needed for error recovery
                    self.error_back_ref = self.upper_bound + 1
                    self.parsing_state = PARSE_ERROR
                    self.error_frames = 0
                    self.error_message = str(exc)
                    # ignore previous frame (as header size was wrong)
                    self.frames.append(self.buffer[self.lower_bound:(
                        self.upper_bound - self.frame_length)])
                    self.lower_bound = self.upper_bound
                else:
                    if self.upper_bound + self.frame_length > self.buffer_length:
                        break
                    self.upper_bound += self.frame_length
            else:
                # error
                if not self.handle_error():
                    break

        frames = self.frames
        self.frames = []

        frames.append(self.buffer[self.lower_bound:self.upper_bound])
        self.buffer = self.buffer[self.upper_bound:]

        if len(frames) > 1:
            frames = b''.join(frames)
        else:
            frames = frames[0]

        return frames

    def clear(self):
      self.buffer = b''

    cdef handle_error(self):
        # when a parsing error occurs, try to parse MIN_SYNC_FRAMES
        while True:
            if self.buffer_length - self.upper_bound < self.max_frame_length:
                return

            # else try to parse a frame
            try:
                if self.handle_headers():
                    self.upper_bound += self.frame_length
                    self.error_frames += 1
            except FrameParsingError:
                # restart from backref
                self.error_frames = 0
                self.lower_bound = self.buffer.find(b'\xff',
                                                         self.error_back_ref)
                if self.lower_bound == -1:
                    # stream is broken
                    raise FrameParsingError(
                        'Broken stream: %s' % self.error_message)

                self.upper_bound = self.lower_bound
                self.error_back_ref = self.upper_bound + 1

            if self.error_frames == MIN_SYNC_FRAMES:
                # sucess
                self.parsing_state = PARSE_HEADER
                return True

            if self.upper_bound - self.error_back_ref + 1 > (
                MIN_SYNC_FRAMES * self.max_frame_length):
                # bad stream
                raise FrameParsingError(
                    'Broken stream: %s' % self.error_message)

    cdef handle_headers(self):
        raise NotImplementedError
