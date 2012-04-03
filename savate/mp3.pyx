# -*- coding: utf-8 -*-

from audio_parser cimport AbstractAudioParser
from audio_parser import FrameParsingError
from struct import Struct


cdef extern from "mp3_static.h":
    int *MPEG_1_LAYER_1
    int *MPEG_1_LAYER_2
    int *MPEG_1_LAYER_3
    int *MPEG_2_LAYER_1
    int *MPEG_2_LAYER_2_3
    int **FREQUENCIES

DEF MPEG_version_1 = 0
DEF MPEG_version_2 = 1
DEF MPEG_version_2_5 = 2

ctypedef enum LAYER:
    LAYER_I
    LAYER_II
    LAYER_III


cdef class MP3Parser(AbstractAudioParser):
    """Handle validation of MP3 frames."""

    unpack = Struct('4B').unpack_from

    def __cinit__(self):
        self.max_frame_length = 4608

    cdef handle_headers(self):
        cdef unsigned char c_buffer[4]
        cdef unsigned char c_field
        cdef int c_version
        cdef LAYER c_layer
        cdef int c_bitrate
        cdef int c_frequency
        cdef int c_padding

        if self.buffer_length - self.upper_bound < 4:
            return

        (
            c_buffer[0],
            c_buffer[1],
            c_buffer[2],
            c_buffer[3],
        ) = self.unpack(self.buffer, self.upper_bound)

        # 11 bits, sync
        if c_buffer[0] != 0xff or c_buffer[1] & 0b11100000 != 0b11100000:
            # TODO sync with stream
            raise FrameParsingError('Invalid sync bits')

        # 2 bits, MPEG audio version ID
        c_field = (c_buffer[1] & 0b00011000)
        if c_field == 0:
            c_version = MPEG_version_2_5
        elif c_field == 0b00010000:
            c_version = MPEG_version_2
        elif c_field == 0b00011000:
            c_version = MPEG_version_1
        else:
            raise FrameParsingError('Invalid MPEG version')

        # 2 bits, Layer
        c_field = c_buffer[1] & 0b00000110
        if c_field == 0b00000010:
            c_layer = LAYER_III
        else:
            raise FrameParsingError('Invalid MPEG layer')

        # 1 bit, CRC

        # 4 bits, bitrate
        c_field = c_buffer[2] >> 4
        if c_version == MPEG_version_1:
            if c_layer == LAYER_III:
                c_bitrate = MPEG_1_LAYER_3[c_field]
            elif c_layer == LAYER_II:
                c_bitrate = MPEG_1_LAYER_2[c_field]
            else:
                c_bitrate = MPEG_1_LAYER_1[c_field]
        else:
            # MPEG version 2 or 2.5
            if c_layer == LAYER_III or c_layer == LAYER_II:
                c_bitrate = MPEG_2_LAYER_2_3[c_field]
            else:
                c_bitrate = MPEG_2_LAYER_1[c_field]

        if c_bitrate == -1:
            raise FrameParsingError('Invalid bitrate identifier')

        # 2 bits, sampling frequency
        c_field = (c_buffer[2] & 0b00001100) >> 2
        c_frequency = FREQUENCIES[c_version][c_field]
        if c_frequency == -1:
            raise FrameParsingError('Invalid sampling rate frequency')

        # 1 bit, padding
        c_padding = (c_buffer[2] & 0b00000010) >> 1

        # 1 bit, private

        # 2 bits, channel mode

        # 2 bits, mode extension

        # 1 bit, copyright

        # 1 bit, original

        # 2 bits, emphasis

        if c_layer == LAYER_I:
            self.frame_length = (12 * c_bitrate / c_frequency + c_padding) << 4
        else:
            # Layer II or III
            self.frame_length = 144 * c_bitrate / c_frequency + c_padding

        return True
