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

You will need `cyhttp11 <http://github.com/cyhttp11>`_ to run savate.

Development
===========

We use `semantic versioning <http://semver.org/>`_ for
versioning. When working on a development release, we append ``~dev``
to the current version to distinguish released versions from
development ones. This has the advantage of working well with Debian's
version scheme, where ``~`` is considered smaller than everything (so
version 1.10.0 is more up to date than 1.10.0~dev).
