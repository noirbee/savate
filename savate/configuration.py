# -*- coding: utf-8 -*-

import collections
import itertools
import urlparse
import socket


class ServerConfiguration(object):

    def __init__(self, server, config_dict):
        self.server = server
        self.config_dict = config_dict

    def __getitem__(self, key):
        return self.config_dict[key]

    def configure(self):
        self.configure_authorization()
        self.configure_status()
        self.configure_relays()

    def find_relay(self, url, path, addr_info = None):
        for relay in itertools.chain(self.server.relays.values(),
                                     (relay for timeout, relay in self.server.relays_to_restart)):
            if (relay.url == url and relay.path == path and
                relay.addr_info == addr_info):
                return relay
        return None

    def find_relay_conf(self, url, path):
        for mount in self.config_dict.get('mounts', []):
            if mount['path'] == path:
                if url in mount.get('source_urls', []):
                    return True
                else:
                    # Relay is not mentioned in the configuration
                    return False
        else:
            # We failed to find the relay or its path in the
            # configuration
            return False

    def reconfigure(self, config_dict):
        self.config_dict = config_dict
        # Drop authorization and status handlers, they will be
        # properly re-created anyway
        self.server.auth_handlers = []
        self.server.status_handlers = {}
        self.configure_authorization()
        self.configure_status()

        # Here comes the tricky part: identifying which relays we need
        # to drop
        tmp_relays = self.server.relays
        self.server.relays = {}

        for relay in tmp_relays.values():
            if self.find_relay_conf(relay.url, relay.path):
                self.server.relays[relay.sock] = relay
            else:
                for sources in self.server.sources.values():
                    for source in sources:
                        if source.sock == relay.sock:
                            self.server.logger.info('Dropping source %s since it has been removed from configuration',
                                                    source)
                            source.close()
                            break
                    else:
                        continue
                    break
                else:
                    # This relay has not been yet added as a source
                    relay.close()

        # Any relay marked to be restarted must be checked as well
        tmp_relays = self.server.relays_to_restart
        self.server.relays_to_restart = collections.deque()

        for timeout, relay in tmp_relays:
            if self.find_relay_conf(relay.url, relay.path):
                self.server.relays_to_restart.append((timeout, relay))

        # Take new configuration into account
        self.configure_relays()

    def configure_relays(self):
        conf = self.config_dict
        server = self.server

        net_resolve_all = conf.get('net_resolve_all', False)

        for mount_conf in conf.get('mounts', {}):
            if 'source_urls' not in mount_conf:
                continue
            path = mount_conf['path']
            for source_url in mount_conf['source_urls']:
                parsed_url = urlparse.urlparse(source_url)
                if parsed_url.scheme in ('udp', 'multicast'):
                    if not self.find_relay(source_url, path):
                        server.logger.info('Trying to relay %s', source_url)
                        server.add_relay(source_url, path)
                else:
                    if mount_conf.get('net_resolve_all', net_resolve_all):
                        for address_info in socket.getaddrinfo(
                            parsed_url.hostname,
                            parsed_url.port,
                            socket.AF_UNSPEC,
                            socket.SOCK_STREAM,
                            socket.IPPROTO_TCP):
                            if not self.find_relay(source_url, path, address_info):
                                server.logger.info('Trying to relay %s from %s:%s', source_url,
                                            address_info[4][0], address_info[4][1])
                                server.add_relay(source_url, path, address_info)
                    else:
                        if not self.find_relay(source_url, path):
                            server.logger.info('Trying to relay %s', source_url)
                            server.add_relay(source_url, path)

    def configure_authorization(self):
        conf = self.config_dict
        server = self.server
        for auth_handler in conf.get('auth', []):
            handler_name = auth_handler['handler']
            handler_module, handler_class = handler_name.rsplit('.', 1)
            handler_module = __import__(handler_module, {}, {}, [''])
            handler_class = getattr(handler_module, handler_class)
            handler_instance = handler_class(server, conf, **auth_handler)
            server.add_auth_handler(handler_instance)

    def configure_status(self):
        conf = self.config_dict
        server = self.server
        for handler_path, status_handler in conf.get('status', {}).items():
            handler_name = status_handler['handler']
            handler_module, handler_class = handler_name.rsplit('.', 1)
            handler_module = __import__(handler_module, {}, {}, [''])
            handler_class = getattr(handler_module, handler_class)
            handler_instance = handler_class(server, conf, **status_handler)
            server.add_status_handler(handler_path, handler_instance)


