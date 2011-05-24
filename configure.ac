#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.67])
AC_INIT([savate], [0.2.0~dev], [nicolas@noirbent.fr])

AC_CONFIG_HEADERS([config.h])

AM_INIT_AUTOMAKE([foreign])

# Checks for programs.
AC_PROG_CC
AC_PROG_LIBTOOL
AM_PATH_PYTHON

AC_SUBST([savatesysconfdir], [\$\(sysconfdir\)/savate])

AC_OUTPUT([
	Makefile
	savate/Makefile
	bin/Makefile
	etc/Makefile
])
