pkgpython_PYTHON = \
	__init__.py \
	auth.py \
	binary_parser.py \
	buffer_event.py \
	clients.py \
	configuration.py \
	flv.py \
	flv_source.py \
	shoutcast_source.py \
	helpers.py \
	looping.py \
	relay.py \
	server.py \
	stats.py \
	status.py \
	sources.py \
	timeouts.py

pkgpyexec_LTLIBRARIES = lllsfd.la

lllsfd_la_CPPFLAGS = ${AM_CPPFLAGS} ${PYTHON_CPPFLAGS}
lllsfd_la_CFLAGS = ${AM_CFLAGS} -fno-strict-aliasing
lllsfd_la_LDFLAGS = ${PYTHON_LDFLAGS} -avoid-version -module

nodist_lllsfd_la_SOURCES = lllsfd.c

if ENABLE_RECVMMSG

pkgpyexec_LTLIBRARIES += recvmmsg.la

recvmmsg_la_CPPFLAGS = ${AM_CPPFLAGS} ${PYTHON_CPPFLAGS}
recvmmsg_la_CFLAGS = ${AM_CFLAGS} -fno-strict-aliasing
recvmmsg_la_LDFLAGS = ${PYTHON_LDFLAGS} -avoid-version -module

nodist_recvmmsg_la_SOURCES = recvmmsg.c

endif

pkgpyexec_LTLIBRARIES += audio_parser.la

audio_parser_la_CPPFLAGS = ${AM_CPPFLAGS} ${PYTHON_CPPFLAGS}
audio_parser_la_CFLAGS = ${AM_CFLAGS} -fno-strict-aliasing
audio_parser_la_LDFLAGS = ${PYTHON_LDFLAGS} -avoid-version -module

nodist_audio_parser_la_SOURCES = audio_parser.c

pkgpyexec_LTLIBRARIES += mp3.la

mp3_la_CPPFLAGS = ${AM_CPPFLAGS} ${PYTHON_CPPFLAGS}
mp3_la_CFLAGS = ${AM_CFLAGS} -fno-strict-aliasing
mp3_la_LDFLAGS = ${PYTHON_LDFLAGS} -avoid-version -module

mp3_la_SOURCES = mp3.c mp3_static.c mp3_static.h

pkgpyexec_LTLIBRARIES += adts.la

adts_la_CPPFLAGS = ${AM_CPPFLAGS} ${PYTHON_CPPFLAGS}
adts_la_CFLAGS = ${AM_CFLAGS} -fno-strict-aliasing
adts_la_LDFLAGS = ${PYTHON_LDFLAGS} -avoid-version -module

adts_la_SOURCES = adts.c

BUILT_SOURCES = lllsfd.c recvmmsg.c audio_parser.c
EXTRA_DIST = lllsfd.pyx lllsfd.pxd recvmmsg.pyx recvmmsg.pxd audio_parser.pyx audio_parser.pxd mp3.pyx adts.pyx ${BUILT_SOURCES}

MAINTAINERCLEANFILES = mp3.c adts.c ${BUILT_SOURCES}

mp3.c: Makefile.in mp3.pyx
	cython --verbose $(srcdir)/$*.pyx -o $@

adts.c: Makefile.in adts.pyx
	cython --verbose $(srcdir)/$*.pyx -o $@

# A kinda clever rule used to avoid writing each Cython compilation
# rule by hand
$(BUILT_SOURCES): %.c: Makefile.in %.pyx %.pxd
	cython --verbose $(srcdir)/$*.pyx -o $@
