# -*- coding: utf-8 -*-

cdef class AbstractAudioParser:
    cdef int parsing_state
    cdef int frame_length
    cdef int max_frame_length
    cdef bytes buffer
    cdef object frames
    cdef int lower_bound
    cdef int upper_bound
    cdef int buffer_length

    # needed for error recovery
    cdef int error_back_ref
    cdef int error_frames
    cdef object error_message

    # methods
    cdef handle_error(self)
    cdef handle_headers(self)
