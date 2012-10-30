========
 savate
========

Experimental live audio/video HTTP server
=========================================

:Manual section: 1


Synopsis
--------

savate [--version] [--help] [options]


Description
-----------

savate is an event-based icecast clone in Python, primarily aimed at
streaming video formats such as FLV or MPEG-TS over a single HTTP
connection.


Options
-------

--version       Display savate's version and exit
-h, --help      Display savate's help message and exit
-c CONFIG, --config=CONFIG      JSON configuration file to use
-l LOGFILE, --logfile=LOGFILE   log file to use
-p PIDFILE, --pidfile=PIDFILE   PID file to use
--background    Run in the background, daemonise (default)
--foreground    Run in the foreground, do not daemonise


Signals
-------

savate reacts to the following signals:

* *SIGTERM*, *SIGINT*: stops the server.
* *SIGHUP*: reloads server configuration.
* *SIGUSR1*: graceful stop. savate will stop accepting any new
  connections, but will continue streaming to connected clients.


Authors
-------

Written by Anaël Beutot, Laurent Defert and Nicolas Noirbent.


Copyright
---------

Copyright © 2011-2012 Nicolas Noirbent.

Copyright © 2011-2012 SmartJog S.A.S.


License AGPLv3+: GNU Affero GPL version 3 or later
<http://gnu.org/licenses/agpl.html>.  This is free software: you are
free to change and redistribute it. There is NO WARRANTY, to the
extent permitted by law.


See also
--------

**savate.json**\(5)
