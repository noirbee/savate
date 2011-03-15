# -*- coding: utf-8 -*-

class Packet(object):

    def __init__(self, header, data, trailer):
        self.header = header
        self.data = data
        self.trailer = trailer

    def is_sync_point(self):
        """
        This is used to define a packet as a synchronisation point,
        i.e. a packet that can be used as a starting point in
        streaming.
        """
        return True

    def is_initial_packet(self):
        """
        This is used to define an initial packet. Initial packets are
        similar to the packet header in that they are sent out first
        to any new client. This is useful for metadata or codec
        configuration packets, i.e. the metadata tag in a FLV stream
        or the decoder configuration record of an AVC video stream.
        """
        return False

    def buffers(self):
        """
        Returns the non-null parts of this packet.
        """
        return (elt for elt in (self.header, self.data, self.trailer) if elt)
