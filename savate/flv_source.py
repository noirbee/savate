# -*- coding: utf-8 -*-

import collections
import itertools
from savate.sources import StreamSource
from savate.flv import FLVHeader, FLVTag, FLVAudioData, FLVVideoData

class FLVSource(StreamSource):

    # Initial burst duration, in milliseconds
    BURST_DURATION = 5 * 1000

    def __init__(self, sock, server, address, content_type, request_parser,
                 path = None, burst_size = None, on_demand = False,
                 keepalive = False):
        StreamSource.__init__(self, sock, server, address, content_type,
                              request_parser, path, burst_size, on_demand,
                              keepalive)
        # Initial buffer data
        self.buffer_data = request_parser.body
        # The FLV stream header
        self.stream_header = None
        # These are the initial setup tags we send out to each new
        # client
        self.initial_tags = collections.deque()
        # Which type of initial tag we already got
        self.got_initial_meta = self.got_initial_audio = self.got_initial_video = False
        # Our current packets group
        self.packets_group = collections.deque()
        # Our current "burst" packets groups list
        self.burst_groups = collections.deque()
        # List of buffers for the "burst" packets
        self.burst_groups_data = collections.deque()
        # At startup we want to parse the stream header
        self.handle_data = self.handle_header

    def on_demand_deactivate(self):
        StreamSource.on_demand_deactivate(self)
        self.stream_header = None
        self.got_initial_meta = self.got_initial_audio = self.got_initial_video = False
        self.initial_tags.clear()
        self.packets_group.clear()
        self.burst_groups.clear()
        self.burst_groups_data.clear()
        self.handle_data = self.handle_header
        self.buffer_data = b''

    def on_demand_connected(self, sock, request_parser):
        self.buffer_data = request_parser.body
        StreamSource.on_demand_connected(self, sock, request_parser)

    def new_client(self, client):
        StreamSource.new_client(self, client)
        if self.stream_header:
            client.add_packet(self.stream_header.raw_data)
        for tag in self.initial_tags:
            client.add_packet(tag.raw_data + tag.body)
        for group_data in self.burst_groups_data:
            client.add_packet(group_data)

    def handle_packet(self, packet):
        self.buffer_data = self.buffer_data + packet
        while self.handle_data():
            pass

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

            if self.check_for_initial_tag(self.current_tag):
                # Tag is one of the initial tag, just publish it
                self.publish_packet(self.current_tag.raw_data)
                self.publish_packet(self.current_tag.body)
            else:
                # We need to add it to our current packets group
                self.add_to_packets_group(self.current_tag)

            self.buffer_data = self.buffer_data[body_length:]
            self.handle_data = self.handle_tag
            return True
        else:
            return False

    def check_for_initial_tag(self, flv_tag):
        if (not self.got_initial_meta and flv_tag.tag_type == 'meta'):
            self.got_initial_meta = True
            self.initial_tags.append(flv_tag)
            return True

        elif (not self.got_initial_audio and flv_tag.tag_type == 'audio'):
            audio_data = FLVAudioData()
            audio_data.parse(flv_tag.body[:audio_data.object_size])
            if (audio_data.sound_format == 'AAC' and
                audio_data.aac_packet_type == audio_data.AAC_SEQUENCE_HEADER):
                self.got_initial_audio = True
                self.initial_tags.append(flv_tag)
                return True

        elif (not self.got_initial_video and flv_tag.tag_type == 'video'):
            video_data = FLVVideoData()
            video_data.parse(flv_tag.body[:video_data.object_size])
            if (video_data.codec == 'AVC' and
                video_data.avc_packet_type == video_data.AVC_SEQUENCE_HEADER):
                self.got_initial_video = True
                self.initial_tags.append(flv_tag)
                return True
        return False

    def add_to_packets_group(self, flv_tag):
        if self.is_sync_point(flv_tag):
            # Current packets group is over, publish all of its
            # packets. It seems buffering is needed to avoid a
            # skyrocketing CPU consumption, hence the ''.join()
            self.publish_packet(b''.join(
                    itertools.chain.from_iterable((tag.raw_data, tag.body) for tag in self.packets_group)))
            # And add it to the burst packets groups list
            self.add_to_burst_groups(self.packets_group)
            # Reset the current packets group
            self.packets_group = collections.deque()
        self.packets_group.append(flv_tag)

    def add_to_burst_groups(self, group):
        while ((len(self.burst_groups) >= 2) and
               ((group[0].timestamp -
                 self.burst_groups[1][0].timestamp) > self.BURST_DURATION)):
            # We try to keep the burst data to at most
            # BURST_DURATION seconds
            self.burst_groups.popleft()
            self.burst_groups_data.popleft()
        self.burst_groups.append(group)
        self.burst_groups_data.append(b''.join(
                itertools.chain.from_iterable((tag.raw_data, tag.body) for tag in group)))

    def is_sync_point(self, flv_tag):
        if self.stream_header.video:
            # If our stream has video, we need to sync on keyframes
            if (flv_tag.tag_type == 'video'):
                video_data = FLVVideoData()
                video_data.parse(flv_tag.body[:video_data.object_size])
                return (video_data.frame_type == 'keyframe')
            else:
                # It's either a non-keyframe video tag or an audio or
                # metadata tag
                return False
        else:
            # Audio only, no sync point needed
            return True
