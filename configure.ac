#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.67])
AC_INIT([pycast2], [0.1.0~dev], [nicolas@noirbent.fr])

AC_CONFIG_HEADERS([config.h])

AM_INIT_AUTOMAKE([foreign])

# Checks for programs.
AC_PROG_CC
AC_PROG_LIBTOOL
AM_PATH_PYTHON
AC_PYTHON_DEVEL([>= 2.5])

AC_SUBST([pycast2sysconfdir], [\$\(sysconfdir\)/pycast2])

AC_OUTPUT([
	Makefile
	pycast2/Makefile
	bin/Makefile
	etc/Makefile
])
