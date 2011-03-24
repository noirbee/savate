#! /usr/bin/python
# -*- coding: utf-8 -*-

import os
import sys
import unittest
import writev

class TestWritev(unittest.TestCase):

    IOV_MAX = 1024

    def setUp(self):
        # FIXME: use tempfile()
        self.output_name = '/tmp/lol.out'
        self.output = open(self.output_name, 'wb+')

    def test_too_many_buffers(self):
        self.assertRaises(IOError, writev.writev, self.output.fileno(),
                          ('a',) * (self.IOV_MAX + 1))

    def test_written(self):
        buff = 'abcdef'
        self.assertEqual(len(buff), writev.writev(self.output.fileno(),
                                                  buff))
        self.output.seek(0)
        self.assertEqual(buff, self.output.read())

    def test_bogus_fd(self):
        buff = 'abcdef'
        self.assertRaises(IOError, writev.writev, -1, buff)

    def test_buffer(self):
        buff = buffer('abcdef')
        self.assertRaises(TypeError, writev.writev, self.output.fileno(),
                          (buff,))

    def tearDown(self):
        self.output.close()
        os.remove(self.output_name)

if __name__ == '__main__':

    unittest.main()
