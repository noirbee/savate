import struct
from enum import Enum
from io import BufferedIOBase
from typing import Any, Callable, ClassVar, Literal, Optional, TypeVar, Union


class BinaryParserError(Exception):
    pass


class BinaryParserEOFError(BinaryParserError):
    pass


class _Invalid(Enum):
    INVALID = object()


class BinaryParser:

    INVALID = _Invalid.INVALID

    parse_fields: ClassVar[tuple[tuple[str, str, Union[bytes, int, Callable[..., Any]]], ...]]
    unpacker: ClassVar[struct.Struct]
    object_size: ClassVar[int]

    def __init_subclass__(cls) -> None:
        # We build our unpacker using the format strings in the
        # second field of self.parse_fields' elements
        cls.unpacker = struct.Struct(">" + "".join(elt[1] for elt in cls.parse_fields))
        # Let's compute the size of the object we're about to parse
        cls.object_size = cls.unpacker.size

    def __init__(self, file_object: Optional[BufferedIOBase] = None) -> None:
        self.file_object = file_object
        self.raw_data = b""

    def parse(self, data: Optional[bytes] = None) -> int:
        if data is not None:
            self.raw_data = data[: self.object_size]
        elif self.file_object:
            self.raw_data = self.file_object.read(self.object_size)
        if self.raw_data == b"":
            raise BinaryParserEOFError("End of file reached")
        if len(self.raw_data) != self.object_size:
            raise BinaryParserError("Not enough data to parse object")
        self.fields = self.unpacker.unpack(self.raw_data)
        self.validate()
        return self.object_size

    def validate(self) -> None:
        for index, field_desc in enumerate(self.parse_fields):
            field, _, validating_object = field_desc
            field_value = self.fields[index]
            if callable(validating_object):
                # We have to pass self as first argument since
                # validating_object is a method
                tmp = validating_object(self, field_value)
                if tmp == self.INVALID:
                    raise BinaryParserError("Failed to validate field %s, value: %s" % (field, str(field_value)))
                else:
                    field_value = tmp
            else:
                if validating_object != field_value:
                    raise BinaryParserError(
                        'Failed to validate field %s: expected "%s", got "%s"'
                        % (field, str(validating_object), str(field_value))
                    )
            setattr(self, field, field_value)

    @staticmethod
    def str_to_long(string: bytes) -> int:
        """
        Parse big-endian bytes into an int.
        """
        counter = 0
        result = 0
        for character in reversed(string):
            result += character << counter * 8
            counter += 1
        return result
