#!/usr/bin/env python3
# Copyright 2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import logging
import sys
import subprocess
import yaml

from contextlib import contextmanager
from functools import partial

from wazo_agentd_client import Client as AgentdClient
from wazo_auth_client import Client as AuthClient
from wazo_websocketd_client import Client as WebsocketdClient

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
)
logger = logging.getLogger('agent-sync')

SECONDARY_HOSTNAME = None


def restart_agentd_on_error(f):
    def inner(*args, **kwargs):
        try:
            result = f(*args, **kwargs)
        except Exception as e:
            logger.info('We got an exception')
            response = getattr(e, 'response', None)
            status_code = getattr(response, 'status_code', None)
            if status_code != 500:
                raise
            logger.info('Got a 500 from wazo-agentd. restarting and retrying')
            subprocess.run(
                [
                    'ssh',
                    '-i', '/root/.ssh/xivo_id_rsa',
                    '-o', 'PreferredAuthentications=publickey',
                    f'root@{SECONDARY_HOSTNAME}',
                    'systemctl', 'restart', 'wazo-agentd'
                ], check=True
            )
            result = f(*args, **kwargs)
        return result
    return inner


class TokenRenewer:

    def __init__(self, hostname, refresh_token, client_id, expiration):
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._expiration = expiration
        self._session = None
        self._new_token_callbacks = []

        self._auth_client = AuthClient(hostname, prefix='api/auth', verify_certificate=False)

    def on_session_expiring_soon(self, event):
        if event['session_uuid'] != self._session:
            return

        self._new_token()

    def register_new_token_callback(self, callback):
        self._new_token_callbacks.append(callback)

    def get_token(self):
        return self._new_token()

    def revoke_token(self, token):
        self._auth_client.token.revoke(token)

    def _new_token(self):
        payload = self._auth_client.token.new(
            'wazo_user',
            refresh_token=self._refresh_token,
            client_id=self._client_id,
            expiration=self._expiration,
        )
        self._session = payload['session_uuid']
        new_token = payload['token']
        for callback in self._new_token_callbacks:
            callback(new_token)
        return new_token


class AgentLoginUpdater:

    LOGGED_IN = 'logged_in'
    LOGGED_OUT = 'logged_out'

    def __init__(self, primary_agentd, secondary_agentd, secondary_token_renewer):
        self._primary = primary_agentd
        self._secondary = secondary_agentd
        self._secondary_token_renewer = secondary_token_renewer

    def on_agent_status_update(self, payload):
        status = payload['data']['status']
        agent_id = payload['data']['agent_id']
        tenant_uuid = payload['tenant_uuid']

        if status == self.LOGGED_IN:
            self._on_agent_login(tenant_uuid, agent_id)
        elif status == self.LOGGED_OUT:
            self._on_agent_logout(tenant_uuid, agent_id)

    @restart_agentd_on_error
    def _on_agent_login(self, tenant_uuid, agent_id):
        status = self._primary.agents.get_agent_status(agent_id)
        with self.secondary_token() as token:
            self._secondary.set_token(token)
            logger.info('login agent %s on %s@%s', agent_id, status.extension, status.context)
            self._secondary.agents.login_agent(agent_id, status.extension, status.context, tenant_uuid=tenant_uuid)

    @restart_agentd_on_error
    def _on_agent_logout(self, tenant_uuid, agent_id):
        with self.secondary_token() as token:
            self._secondary.set_token(token)
            logger.info('logoff agent %s', agent_id)
            self._secondary.agents.logoff_agent(agent_id, tenant_uuid=tenant_uuid)

    @contextmanager
    def secondary_token(self):
        token = self._secondary_token_renewer.get_token()
        try:
            yield token
        finally:
            self._secondary_token_renewer.revoke_token(token)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', default='/etc/wazo-agent-sync.yml')
    args = parser.parse_args()

    config = yaml.safe_load(open(args.config))
    logger.debug('starting with coonfig: %s', config)
    global SECONDARY_HOSTNAME
    SECONDARY_HOSTNAME = config['secondary_hostname']

    primary_token_renewer = TokenRenewer(config['primary_hostname'], config['refresh_token'], config['client_id'], 3600 * 12)
    secondary_token_renewer = TokenRenewer(config['secondary_hostname'], config['refresh_token'], config['client_id'], 3600 * 12)

    primary_token = primary_token_renewer.get_token()
    ws = WebsocketdClient(config['primary_hostname'], token=primary_token, verify_certificate=False)
    primary_agentd = AgentdClient(config['primary_hostname'], token=primary_token, verify_certificate=False)
    secondary_agentd = AgentdClient(config['secondary_hostname'], token=None, verify_certificate=False)

    primary_token_renewer.register_new_token_callback(ws.update_token)
    primary_token_renewer.register_new_token_callback(primary_agentd.set_token)

    agent_status_updater = AgentLoginUpdater(primary_agentd, secondary_agentd, secondary_token_renewer)

    ws.on('agent_status_update', agent_status_updater.on_agent_status_update)
    ws.on('auth_session_expire_soon', primary_token_renewer.on_session_expiring_soon)

    print('starting...')
    ws.run()
    print('done')


if __name__ == '__main__':
    main()
