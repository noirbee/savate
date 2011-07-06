# -*- coding: utf-8 -*-

import struct


class BinaryParserError(Exception):
    pass


class BinaryParserEOFError(BinaryParserError):
    pass


class BinaryParser(object):

    INVALID = object()

    def __init__(self, file_object = None):
        self.file_object = file_object
        # We build our unpacker using the format strings in the
        # second field of self.parse_fields' elements
        self.unpacker = struct.Struct('>' + ''.join(elt[1] for elt in self.parse_fields))
        # Let's compute the size of the object we're about to parse
        self.object_size = self.unpacker.size

    def parse(self, data = None):
        if data is not None:
            self.raw_data = data[:self.object_size]
        else:
            self.raw_data = self.file_object.read(self.object_size)
        if self.raw_data == '':
            raise BinaryParserEOFError('End of file reached')
        if len(self.raw_data) != self.object_size:
            raise BinaryParserError('Not enough data to parse object')
        self.fields = self.unpacker.unpack(self.raw_data)
        self.validate()
        return self.object_size

    def validate(self):
        for index, field_desc in enumerate(self.parse_fields):
            if len(field_desc) < 3:
                # No validating object provided, skip it
                continue
            field, _unpack_str, validating_object = field_desc
            field_value = self.fields[index]
            if callable(validating_object):
                # We have to pass self as first argument since
                # validating_object is a method
                tmp = validating_object(self, field_value)
                if tmp == self.INVALID:
                    raise BinaryParserError('Failed to validate field %s, value: %s' % (field, str(field_value)))
                else:
                    field_value = tmp
            else:
                if validating_object != field_value:
                    raise BinaryParserError('Failed to validate field %s: expected "%s", got "%s"' %
                                            (field, str(validating_object), str(field_value)))
            setattr(self, field, field_value)

    # Some helpers
    BIG_ENDIAN = object()
    LITTLE_ENDIAN = object()

    @classmethod
    def object_size(cls):
        return struct.calcsize('>' + ''.join(elt[1] for elt in cls.parse_fields))

    @staticmethod
    def str_to_long(string, endianness = BIG_ENDIAN):
        if endianness == BinaryParser.BIG_ENDIAN:
            string = reversed(string)
        counter = 0
        result = 0
        for character in string:
            result += ord(character) << counter * 8
            counter += 1
        return result
