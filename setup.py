#! /usr/bin/python
# -*- coding: utf-8 -*-

from distutils.core import setup
from distutils.extension import Extension
from Cython.Distutils import build_ext

ext_modules = [Extension('writev', ['writev.pyx', 'writev.pxd'])]

setup(
    name = 'writev',
    description = "Cython binding for writev()",
    cmdclass = {'build_ext': build_ext},
    ext_modules = ext_modules,
)

