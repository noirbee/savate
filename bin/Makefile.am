bin_SCRIPTS = pycast2 httpkiller

edit = $(SED) \
	-e 's|@pycast2sysconfdir[@]|$(pycast2sysconfdir)|g' \
	-e 's|@pyexecdir[@]|$(pyexecdir)|g' \
        -e 's|@PACKAGE_NAME[@]|$(PACKAGE_NAME)|g' \
	-e 's|@VERSION[@]|$(VERSION)|g'

$(bin_SCRIPTS): $(bin_SCRIPTS:=.in) Makefile
	$(edit) $(srcdir)/$@.in > $(builddir)/$@

CLEANFILES = $(bin_SCRIPTS)
EXTRA_DIST = $(bin_SCRIPTS:=.in)
