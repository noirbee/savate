# -*- coding: utf-8 -*-

import collections
from pycast2.sources import BufferedRawSource, StreamSource
from pycast2.flv import FLVHeader, FLVTag, FLVAudioData, FLVVideoData
from pycast2 import looping
from pycast2 import helpers

class FLVSource(BufferedRawSource):

    # Initial burst duration, in milliseconds
    BURST_DURATION = 5 * 1000

    def __init__(self, sock, server, address, content_type, request_parser, path = None):
        BufferedRawSource.__init__(self, sock, server, address, content_type, request_parser, path)
        # Initial buffer data
        self.buffer_data = request_parser.body
        # The FLV stream header
        self.stream_header = None
        # These are the initial setup tags we send out to each new
        # client
        self.initial_tags = collections.deque()
        # Which type of initial tag we already got
        self.got_initial_meta = self.got_initial_audio = self.got_initial_video = False
        # Our current "burst" packets groups list
        self.burst_groups = collections.deque()
        # At startup we want to parse the stream header
        self.handle_data = self.handle_header

    def new_client(self, client):
        if self.stream_header:
            client.add_packet(self.stream_header.raw_data)
        for tag in self.initial_tags:
            client.add_packet(tag.raw_data)
            client.add_packet(tag.body)
        for group in self.burst_groups:
            for tag in group:
                client.add_packet(tag.raw_data)
                client.add_packet(tag.body)

    def handle_event(self, eventmask):
        if eventmask & looping.POLLIN:
            while True:
                packet = helpers.handle_eagain(self.sock.recv, self.RECV_BUFFER_SIZE)
                if packet == None:
                    # EAGAIN
                    break
                elif packet == b'':
                    # End of stream
                    self.server.logger.warn('End of stream for %s, %s', self.path, (self.sock, self.address))
                    self.server.remove_source(self)
                    # FIXME: publish "EOS" packet
                    break
                else:
                    self.buffer_data = self.buffer_data + packet
                    while self.handle_data():
                        pass
        else:
            self.server.logger.error('%s: unexpected eventmask %s', self, eventmask)

    def handle_header(self):
        if len(self.buffer_data) >= FLVHeader.object_size():
            # We can try and parse the stream header
            self.stream_header = FLVHeader()
            nb_parsed = self.stream_header.parse(self.buffer_data)
            self.publish_packet(self.stream_header.raw_data)
            self.buffer_data = self.buffer_data[nb_parsed:]
            self.handle_data = self.handle_tag
            return True
        else:
            return False

    def handle_tag(self):
        if len(self.buffer_data) >= FLVTag.object_size():
            # We can try and parse one FLV tag
            self.current_tag = FLVTag()
            nb_parsed = self.current_tag.parse(self.buffer_data)
            self.buffer_data = self.buffer_data[nb_parsed:]
            self.handle_data = self.handle_tag_body
            return True
        else:
            return False

    def handle_tag_body(self):
        body_length = (self.current_tag.data_size +
                       self.current_tag.TRAILER_SIZE)
        if len(self.buffer_data) >= body_length:
            self.current_tag.body = self.buffer_data[:body_length]
            self.check_for_initial_tag(self.current_tag)
            self.add_to_burst_groups(self.current_tag)
            self.publish_packet(self.current_tag.raw_data)
            self.publish_packet(self.current_tag.body)
            self.buffer_data = self.buffer_data[body_length:]
            self.handle_data = self.handle_tag
            return True
        else:
            return False

    def check_for_initial_tag(self, flv_tag):
        if (not self.got_initial_meta and flv_tag.tag_type == 'meta'):
            self.got_initial_meta = True
            self.initial_tags.append(flv_tag)

        elif (not self.got_initial_audio and flv_tag.tag_type == 'audio'):
            audio_data = FLVAudioData()
            audio_data.parse(flv_tag.body[:audio_data.object_size])
            if (audio_data.sound_format == 'AAC' and
                audio_data.aac_packet_type == audio_data.AAC_SEQUENCE_HEADER):
                self.got_initial_audio = True
                self.initial_tags.append(flv_tag)

        elif (not self.got_initial_video and flv_tag.tag_type == 'video'):
            video_data = FLVVideoData()
            video_data.parse(flv_tag.body[:video_data.object_size])
            if (video_data.codec == 'AVC' and
                video_data.avc_packet_type == video_data.AVC_SEQUENCE_HEADER):
                self.got_initial_video = True
                self.initial_tags.append(flv_tag)

    def add_to_burst_groups(self, flv_tag):
        if self.is_sync_point(flv_tag) or len(self.burst_groups) == 0:
            group = collections.deque((flv_tag,))
            while ((len(self.burst_groups) >= 2) and
                   ((flv_tag.timestamp -
                     self.burst_groups[1][0].timestamp) > self.BURST_DURATION)):
                # We try to keep the burst data to at most
                # BURST_DURATION seconds
                self.burst_groups.popleft()
            self.burst_groups.append(group)
        else:
            self.burst_groups[-1].append(flv_tag)

    def is_sync_point(self, flv_tag):
        if (flv_tag.tag_type == 'video'):
            video_data = FLVVideoData()
            video_data.parse(flv_tag.body[:video_data.object_size])
            return (video_data.frame_type == 'keyframe')
        else:
            return True
