dist_man1_MANS = savate.man
dist_man5_MANS = savate.json.man


EXTRA_DIST = $(dist_man1_MANS:.man=.rst) $(dist_man5_MANS:.man=.rst)
DISTCLEANFILES = $(dist_man1_MANS) $(dist_man5_MANS)

SUFFIXES = .rst

.rst.man:
	$(RST2MAN) $< $@
