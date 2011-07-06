# -*- coding: utf-8 -*-

from savate.binary_parser import BinaryParser


class FLVHeader(BinaryParser):

    AUDIO_PRESENT = 4
    VIDEO_PRESENT = 1

    def flv_header_flags(self, field_value):
        self.audio = (field_value & self.AUDIO_PRESENT) == self.AUDIO_PRESENT
        self.video = (field_value & self.VIDEO_PRESENT) == self.VIDEO_PRESENT
        return field_value

    parse_fields = (
        ('signature', '3s', 'FLV'),
        ('version', 'B', 1),
        ('flags', 'B', flv_header_flags),
        ('data_offset', 'I', 9),
        ('previous_tag_size', 'I', 0),
        )


class FLVTag(BinaryParser):

    TYPE_AUDIO = 8
    TYPE_VIDEO = 9
    TYPE_META = 18

    tag_types = {
        TYPE_AUDIO: 'audio',
        TYPE_VIDEO: 'video',
        TYPE_META: 'meta',
        }

    TRAILER_SIZE = 4

    def flv_tag_type(self, field_value):
        if field_value not in self.tag_types.keys():
            return BinaryParser.INVALID
        self.tag_type = self.tag_types[field_value]
        return field_value

    def flv_data_size(self, field_value):
        return BinaryParser.str_to_long(field_value)

    def flv_tag_timestamp(self, field_value):
        timestamp_extended = ord(field_value[3]) << 24
        return BinaryParser.str_to_long(field_value[:3]) + timestamp_extended

    parse_fields = (
        ('tag_type_id', 'B', flv_tag_type),
        ('data_size', '3s', flv_data_size),
        ('timestamp', '4s', flv_tag_timestamp),
        ('stream_id', '3s', '\x00' * 3),
        )

    def __str__(self):
        return '<FLVTag type %s, time %d, size %d>' % (self.tag_type, self.timestamp, self.data_size)


class FLVVideoData(BinaryParser):

    KEYFRAME = 1
    INTER_FRAME = 2
    DISPOSABLE_INTER_FRAME = 3
    GENERATED_KEYFRAME = 4
    VIDEO_INFO_FRAME = 5

    frame_types = {
        KEYFRAME: 'keyframe',
        INTER_FRAME: 'inter frame',
        DISPOSABLE_INTER_FRAME: 'disposable inter frame',
        GENERATED_KEYFRAME: 'generated keyframe',
        VIDEO_INFO_FRAME: 'video info/command frame',
        }

    JPEG = 1
    SORENSON_H263 = 2
    SCREEN_VIDEO = 3
    ON2_VP6 = 4
    ON2_VP6_ALPHA = 5
    SCREEN_VIDEO_V2 = 6
    AVC = 7

    codecs = {
        JPEG: 'JPEG',
        SORENSON_H263: 'Sorenson H.263',
        SCREEN_VIDEO: 'Screen video',
        ON2_VP6: 'On2 VP6',
        ON2_VP6_ALPHA: 'On2 VP6 with alpha channel',
        SCREEN_VIDEO_V2: 'Screen video version 2',
        AVC: 'AVC',
        }

    AVC_SEQUENCE_HEADER = 0
    AVC_NALU = 1
    AVC_SEQUENCE_END = 2

    def video_tag_info(self, field_value):
        self.frame_type_id = field_value >> 4
        if self.frame_type_id not in self.frame_types.keys():
            return BinaryParser.INVALID
        self.frame_type = self.frame_types[self.frame_type_id]

        self.codec_id = field_value & 0x0f
        if self.codec_id not in self.codecs.keys():
            return BinaryParser.INVALID
        self.codec = self.codecs[self.codec_id]

    parse_fields = (
        ('frame_type_and_codec', 'B', video_tag_info),
        ('avc_packet_type', 'B', lambda instance, elt: elt),
        )


class FLVAudioData(BinaryParser):

    LINEAR_PCM_HOST_ENDIAN = 0
    ADPCM = 1
    MP3 = 2
    LINEAR_PCM_LITTLE_ENDIAN = 3
    NELLYMOSER_16_KHZ_MONO = 4
    NELLYMOSER_8_KHZ_MONO = 5
    NELLYMOSER = 6
    G711_A_LAW_LOG_PCM = 7
    G711_MU_LAW_LOG_PCM = 8
    RESERVED = 9
    AAC = 10
    SPEEX = 11
    MP3_8KHZ = 14
    DEVICE_SPECIFIC = 15

    sound_formats = {
        LINEAR_PCM_HOST_ENDIAN: 'Linear PCM, platform endian',
        ADPCM: 'ADPCM',
        MP3: 'MP3',
        LINEAR_PCM_LITTLE_ENDIAN: 'Linear PCM, little endian',
        NELLYMOSER_16_KHZ_MONO: 'Nellymoser, 16-kHz mono',
        NELLYMOSER_8_KHZ_MONO: 'Nellymoser, 8-kHz mono',
        NELLYMOSER: 'Nellymoser',
        G711_A_LAW_LOG_PCM: 'G.711 A-law logarithmic PCM',
        G711_MU_LAW_LOG_PCM: 'G.711 mu-law logarithmic PCM',
        RESERVED: 'reserved',
        AAC: 'AAC',
        SPEEX: 'Speex',
        MP3_8KHZ: 'MP3 8-kHz',
        DEVICE_SPECIFIC: 'Device-specific sound',
        }

    AAC_SEQUENCE_HEADER = 0
    AAC_RAW = 1

    def audio_data_info(self, field_value):
        self.sound_format_id = field_value >> 4
        if self.sound_format_id not in self.sound_formats.keys():
            return BinaryParser.INVALID
        self.sound_format = self.sound_formats[self.sound_format_id]

    parse_fields = (
        ('audio_data', 'B', audio_data_info),
        ('aac_packet_type', 'B', lambda instance, elt: elt),
        )
