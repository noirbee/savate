========
 savate
========

savate is an experimental live audio/video HTTP streaming server.

License
=======

savate is © 2011 Nicolas Noirbent, and is available under the AGPL3+
license.

Build and installation
=======================

Bootstrapping
-------------

savate uses the autotools for its build system.

If you checked out code from the git repository, you will need
autoconf and automake to generate the configure script and Makefiles.

To generate them, simply run::

    $ autoreconf -fvi

Building
--------

If building from the git repository, you will need `Cython
<http://cython.org/>`_.

You need to be able to build Python extensions to build savate.

savate builds like your typical autotools-based project::

    $ ./configure && make && make install

Runtime
-------

You will need `cyhttp11 <http://github.com/noirbee/cyhttp11>`_ to run
savate.

Development
===========

We use `semantic versioning <http://semver.org/>`_ for
versioning. When working on a development release, we append ``~dev``
to the current version to distinguish released versions from
development ones. This has the advantage of working well with Debian's
version scheme, where ``~`` is considered smaller than everything (so
version 1.10.0 is more up to date than 1.10.0~dev).

TODO
====

* savate currently uses an homemade epoll-based I/O event loop. While
  it does the job, it is (obviously) lacking some nice features from a
  dedicated event loop (most notably timers and a wider platform
  support). `pyev <http://code.google.com/p/pyev/>`_ looks like a good
  fit, although it is lacking edge-triggered operation (this
  particular feature does not seem very common / used among other
  event loops). `tornado <http://www.tornadoweb.org/>`_ looks very
  close in terms of API, and would apparently not forbid us to go with
  edge-triggered operation, so it may well be a better short-term
  solution; it may also give us access to other tornado-based projects
  (see https://github.com/facebook/tornado/wiki/Links)
* Smarter dead/slow clients detection for FLV streaming. Instead of
  I/O starvation ("x milliseconds without I/O"), check for clients
  that are too late wrt the live stream.
* True HTTP/1.1; first and foremost, chunked transfer-encoding support
  for sources.
* Free/open formats support: Ogg/Vorbis/Theora/WebM.
* Raw AAC support. Note that savate already supports AAC-only FLV
  streams.
* File fallback on source takedown / failure.
* On-demand relaying.
* Master / slave operation, where a slave savate instance will
  re-stream its master(s)'s streams.
* Multi-process / multi-thread operation.
