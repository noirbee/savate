pkgpyexec_PYTHON = \
	__init__.py \
	binary_parser.py \
	buffer_event.py \
	clients.py \
	flv.py \
	flv_source.py \
	helpers.py \
	looping.py \
	relay.py \
	server.py \
	sources.py

pkgpyexec_LTLIBRARIES = writev.la
writev_la_SOURCES = writev.c
writev_la_CPPFLAGS = ${AM_CPPFLAGS} ${PYTHON_CPPFLAGS}
writev_la_CFLAGS = ${AM_CFLAGS} -fno-strict-aliasing
writev_la_LDFLAGS = ${PYTHON_LDFLAGS} -avoid-version -module

EXTRA_DIST = writev.pxd writev.pyx ${BUILT_SOURCES}

writev.c: Makefile.in writev.pyx writev.pxd
	cython --verbose writev.pyx
