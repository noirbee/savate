#                                               -*- Autoconf -*-
# Process this file with autoconf to produce a configure script.

AC_PREREQ([2.67])
AC_INIT([savate], [0.5.1~dev], [nicolas@noirbent.fr])

AC_CONFIG_HEADERS([config.h])

AM_INIT_AUTOMAKE([foreign])
m4_ifdef([AM_SILENT_RULES], [AM_SILENT_RULES])

# Checks for programs.
AC_PROG_CC
AC_PROG_LIBTOOL
AM_PATH_PYTHON
AC_PYTHON_DEVEL
AC_PATH_PROG(RST2MAN, rst2man)


# recvmmsg() support, first off the CLI switch, disabled by default
AC_ARG_ENABLE([recvmmsg],
                [AS_HELP_STRING([--enable-recvmmsg], [use recvmmsg() if available @<:@default=no@:>@])],
                [
                case "${enableval}" in
                     yes) want_recvmmsg=yes ;;
                     no) want_recvmmsg=no ;;
                     *) AC_MSG_ERROR([bad value ${enableval} for --enable-recvmmsg]) ;;
                esac
                ],
                [want_recvmmsg=no]
                )
# Then if the user enabled it, test for existence of the function
AS_IF([test "x$want_recvmmsg" != xno],
            [AC_CHECK_FUNC([recvmmsg])]
            )
# And finally define the automake conditional used by our Makefile.am
AM_CONDITIONAL([ENABLE_RECVMMSG], [test "x$ac_cv_func_recvmmsg" = xyes])

AC_SUBST([savatesysconfdir], [\$\(sysconfdir\)/savate])

AC_OUTPUT([
	Makefile
	savate/Makefile
	bin/Makefile
	etc/Makefile
	doc/Makefile
])
