dist_man8_MANS = savate.man

EXTRA_DIST = $(dist_man8_MANS:.man=.rst)
DISTCLEANFILES = $(dist_man8_MANS)

SUFFIXES = .rst

.rst.man:
	$(RST2MAN) $< $@
