=============
 savate.json
=============

JSON configuration file for savate
==================================

:Manual section: 5


Description
-----------

The configuration for **savate**\(8) is stored as a JSON (<http://json.org/>) dictionary.

The dictionary is divided in several configuration sections:

* the top or global section, containing server-wide variables.
* the `mounts` section, containing the list of streams, relays etc. for this **savate** instance.
* the `statistics` section, containing the configuration for logging handlers.
* the `auth` section, containing the configuration for authentication/authorisation handlers.
* the `status` section, containing the configuration for **savate**\'s status handlers.


A note on handlers
~~~~~~~~~~~~~~~~~~

**savate** uses runtime-pluggable handlers for a number of tasks,
notably logging, statistics, authentication/authorisation, and status
pages. These handlers are usually Python classes or functions
implementing one of the corresponding handler API.


Options list
------------

Here follows the list of regular configuration options for
**savate**. Various pluggable handlers, notably the `auth` ones, can
add options in some sections, notably the `mounts` one.

Some options can be specified several times in different sections,
with the one in the deepest section overriding the others. For
example, you can specify a server-wide `burst_size` in the global
configuration, and then use another for a specific mount point. The
sections where an option can appear are specified after the
description, in parentheses.


`bind`  The IP address to bind to (global)

`port`  The IP port to bind to (global)

`log_file`      The path to savate's log file (global)

`pid_file`      The path to savate's PID file (global)

`net_resolve_all`       Boolean. Whether to fully resolve DNS entries to
multiple IPs when relaying an URL. This means savate will try to relay
the specified with each IP obtained. (global, `mounts`)

`burst_size`    The burst buffer size, in bytes. This represents the
amount of data to send to a client at connection time, to quickly fill
the player's playout buffer, making for a quicker startup on the
client side. (global, `mounts`)

`on_demand`     Boolean. When relaying an URL, only start pulling it when
a client connects to the mount point. (global, `mounts`)

`keepalive`     When using on-demand relaying, this represents the amount
of time, in seconds, that savate will keep pulling the URL once there
are no more clients using it. (global, `mounts`)

`clients_limit` The maximum number of streaming clients allowed. Over
this limit, savate will send a 503 HTTP response to a new client. Note
that this is only used for streaming clients; sources and status pages
clients are not affected by this limit. (global)


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

**savate**\(8)
