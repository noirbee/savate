# -*- coding: utf-8 -*-

from audio_parser cimport AbstractAudioParser
from audio_parser import FrameParsingError


cdef class ADTSParser(AbstractAudioParser):
    """Handle validation of ADTS frames."""

    cdef handle_headers(self):
        cdef unsigned char c_buffer[7]

        if self.buffer_length - self.upper_bound < 7:
            return

        (
            c_buffer[0],
            c_buffer[1],
            c_buffer[2],
            c_buffer[3],
            c_buffer[4],
            c_buffer[5],
            c_buffer[6],
        ) = self.unpack(self.buffer, self.upper_bound)

        # 11 bits, sync
        if c_buffer[0] != 0xff or c_buffer[1] & 0b11100000 != 0b11100000:
            # TODO sync with stream
            raise FrameParsingError('Invalid sync bits')

        # 1 bit, MPEG version

        # 2 bits, layer

        # 1 bit, CRC ? 0 : 1

        # 2 bits, MPEG-4 audio object type minus 1

        # 4 bits, MPEG-4 sampling frequency index

        # 1 bit, private stream

        # 3 bits, MPEG-4 channel configuration

        # 1 bit, originality

        # 1 bit, home

        # 1 bit, copyrighted stream

        # 1 bit, copyright start

        # 13 bits, frame length
        self.frame_length = <unsigned int>c_buffer[5] >> 5
        self.frame_length += (<unsigned int>c_buffer[4]) << 3
        self.frame_length += ((<unsigned int>c_buffer[3]) & 3) << 11

        # 11 bits, buffer fullness

        # 2 bits, number of AAC frames in ADTS frame minus 1

        # 16 bits, CRC

        return True
