# -*- coding: utf-8 -*-

import base64
import collections
import hashlib
import time

from helpers import HTTPResponse

AUTH_SUCCESS = HTTPResponse(200, b'OK')
AUTH_FAILURE = HTTPResponse(403, b'Forbidden')

class AbstractAuthorization(object):

    def __init__(self, server, server_config, **config_dict):
        self.server = server
        self.server_config = server_config
        self.config = config_dict

    def authorize(self, client_address, client_request):
        # True: OK, go on serving
        # False: NOK, 403
        # None: I don't know, move on to next auth handler
        return None


class AbstractBasicAuthorization(AbstractAuthorization):
    """
    HTTP Basic authorization scheme support (RFC 2617)
    """

    def __init__(self, server, server_config, **config_dict):
        AbstractAuthorization.__init__(self, server, server_config, **config_dict)
        self.global_user = config_dict.get(self.USER_ITEM)
        self.global_password = config_dict.get(self.PASSWORD_ITEM)
        self.protected_paths = collections.defaultdict(lambda: {'user': self.global_user,
                                                                'password': self.global_password})
        for mount_config in self.server_config.get('mounts', []):
            self.protected_paths[mount_config['path']] = {
                'user': mount_config.get(self.USER_ITEM, self.global_user),
                'password': mount_config.get(self.PASSWORD_ITEM, self.global_password),
                }

    def authorize(self, client_address, client_request):
        path = client_request.request_path
        protected_user = self.protected_paths[path]['user']
        protected_password = self.protected_paths[path]['password']
        if (protected_user, protected_password) != (None, None):
            # This path is protected, did the client provide a correct
            # Authorization header ?
            auth_header = client_request.headers.get(b'Authorization')
            if auth_header:
                if not auth_header.startswith(b'Basic '):
                    # We only know about the Basic scheme
                    # FIXME: Digest scheme support ?
                    return AUTH_FAILURE
                else:
                    try:
                        auth_string = base64.b64decode(auth_header.lstrip(b'Basic'))
                    except TypeError:
                        return AUTH_FAILURE
                    if b':' not in auth_string:
                        # Malformed authorization string
                        return AUTH_FAILURE
                    else:
                        auth_user, auth_password = auth_string.split(b':', 1)
                        if protected_user and protected_user != auth_user:
                            return AUTH_FAILURE
                        if protected_password and protected_password != auth_password:
                            return AUTH_FAILURE
                        else:
                            return AUTH_SUCCESS
            else:
                # No Authorization header provided
                return AUTH_FAILURE
        else:
            return None


class SourceBasicAuthorization(AbstractBasicAuthorization):

    USER_ITEM = 'source_user'
    PASSWORD_ITEM = 'source_password'


class ClientBasicAuthorization(AbstractBasicAuthorization):

    USER_ITEM = 'user'
    PASSWORD_ITEM = 'password'


class BasicAuthorization(AbstractAuthorization):

    def __init__(self, server, server_config, **config_dict):
        AbstractAuthorization.__init__(self, server, server_config, **config_dict)
        self.source_auth = SourceBasicAuthorization(server, server_config, **config_dict)
        self.client_auth = ClientBasicAuthorization(server, server_config, **config_dict)

    def authorize(self, client_address, client_request):
        if client_request.request_method in [b'PUT', b'SOURCE', b'POST']:
            return self.source_auth.authorize(client_address, client_request)
        elif client_request.request_method in [b'GET']:
            return self.client_auth.authorize(client_address, client_request)
        else:
            return None


class TokenAuthorization(AbstractAuthorization):

    def __init__(self, server, server_config, **config_dict):
        AbstractAuthorization.__init__(self, server, server_config, **config_dict)
        self.global_secret = config_dict.get('secret')
        self.global_timeout = config_dict.get('timeout')
        self.global_prefix = config_dict.get('prefix', '')
        self.protected_paths = collections.defaultdict(lambda: {'secret': self.global_secret,
                                                                'timeout': self.global_timeout,
                                                                'prefix': self.global_prefix,
                                                                })
        for mount_config in self.server_config.get('mounts', []):
            self.protected_paths[mount_config['path']] = {
                'secret': mount_config.get('secret', self.global_secret),
                'timeout': mount_config.get('token_timeout', self.global_timeout),
                'prefix': mount_config.get('token_prefix', self.global_prefix),
                }

    def authorize(self, client_address, client_request):
        path = client_request.request_path
        secret = self.protected_paths[path]['secret']
        timeout = self.protected_paths[path]['timeout']
        prefix = self.protected_paths[path]['prefix']
        if secret != None:
            # This path is token-protected
            if not path.startswith(prefix):
                # Incorrect prefix
                # FIXME: note that something is probably wrong with
                # the configuration here, we should probably log /
                # warn the admin
                return AUTH_FAILURE
            else:
                # Get rid of prefix and slashes
                path = path[len(prefix):].strip('/')
                if path.count('/') < 2:
                    # Not enough components to be a tokenised path
                    return AUTH_FAILURE
                # Split into token, timestamp, and path
                token, timestamp, path = path.split('/', 2)
                # Check the token is valid
                if token != hashlib.md5(secret + '/' + path + timestamp).hexdigest():
                    # Invalid token
                    return AUTH_FAILURE
                # Check the timeout is not expired, if needed
                if timeout and (int(time.time()) - timeout) > int(timestamp, 16):
                    return AUTH_FAILURE

                # We have to remove the token and timestamp from the original
                # path or else the server won't find the correct handler
                # afterwards
                client_request.request_path = '/'.join([prefix, path])
                print client_request.request_path
                return AUTH_SUCCESS

        return None
