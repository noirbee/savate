pkgpyexec_PYTHON = \
	__init__.py \
	auth.py \
	binary_parser.py \
	buffer_event.py \
	clients.py \
	configuration.py \
	flv.py \
	flv_source.py \
	helpers.py \
	looping.py \
	relay.py \
	server.py \
	status.py \
	sources.py \
	timeouts.py

pkgpyexec_LTLIBRARIES = lllsfd.la
lllsfd_la_CPPFLAGS = ${AM_CPPFLAGS} ${PYTHON_CPPFLAGS}
lllsfd_la_CFLAGS = ${AM_CFLAGS} -fno-strict-aliasing
lllsfd_la_LDFLAGS = ${PYTHON_LDFLAGS} -avoid-version -module

nodist_lllsfd_la_SOURCES = ${BUILT_SOURCES}

EXTRA_DIST = lllsfd.pyx lllsfd.pxd ${BUILT_SOURCES}

BUILT_SOURCES = lllsfd.c
CLEANFILES = ${BUILT_SOURCES}

lllsfd.c: Makefile.in lllsfd.pyx lllsfd.pxd
	cython --verbose lllsfd.pyx
