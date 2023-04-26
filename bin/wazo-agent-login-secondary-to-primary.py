#!/usr/bin/env python3
# Copyright 2023 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import logging
import sys

import yaml
import requests

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
)
logger = logging.getLogger('agent-sync')

EXPIRATION = 300
VERIFY = True

def get_token(hostname, config):
    payload = {'refresh_token': config['refresh_token'], 'client_id': config['client_id'], 'expiration': EXPIRATION}
    response = requests.post(
        f'https://{hostname}/api/auth/0.1/token',
        json=payload,
        headers={'Accept': 'application/json'},
        verify=VERIFY,
    )

    if response.status_code != 200:
        response.raise_for_status()

    return response.json()['data']['token']


def list_agent_statuses(hostname, token):
    response = requests.get(
        f'https://{hostname}/api/agentd/1.0/agents',
        params={'recurse': True},
        headers={'X-Auth-Token': token, 'Accept': 'application/json'},
        verify=VERIFY,
    )

    if response.status_code != 200:
        response.raise_for_status()

    return response.json()


def log_out_agent(hostname, token, tenant_uuid, agent_id):
    headers = {'X-Auth-Token': token, 'Accept': 'application/json', 'Wazo-Tenant': tenant_uuid}
    requests.post(
        f'https://{hostname}/api/agentd/1.0/agents/by-id/{agent_id}/logoff',
        headers=headers,
        verify=VERIFY,
    ).raise_for_status()


def log_in_agent(hostname, token, tenant_uuid, agent_id, context, extension):
    headers = {
        'X-Auth-Token': token,
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Wazo-Tenant': tenant_uuid,
    }
    requests.post(
        f'https://{hostname}/api/agentd/1.0/agents/by-id/{agent_id}/login',
        headers=headers,
        json={'extension': extension, 'context': context},
        verify=VERIFY,
    ).raise_for_status()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', default='/etc/wazo-agent-sync.yml')
    parser.add_argument('-i', '--insecure', action='store_true', default=False)
    args = parser.parse_args()
    config = yaml.safe_load(open(args.config))

    global VERIFY
    if args.insecure:
        VERIFY = False

    primary_hostname = config['primary_hostname']
    secondary_hostname = config['secondary_hostname']

    secondary_token = get_token(secondary_hostname, config)
    secondary_agents = list_agent_statuses(secondary_hostname, secondary_token)
    primary_token = get_token(primary_hostname, config)
    primary_agents = list_agent_statuses(primary_hostname, primary_token)

    logged_in_status = []
    logged_out_status = []

    for agent_status in secondary_agents:
        if agent_status['logged']:
            logged_in_status.append(agent_status)
        else:
            logged_out_status.append(agent_status)

    to_login = []
    to_logout = []
    for agent_status in primary_agents:
        if agent_status['logged']:
            for status in logged_out_status:
                if status['id'] != agent_status['id']:
                    continue
                to_logout.append(agent_status)
                break
        else:
            for status in logged_in_status:
                if status['id'] != agent_status['id']:
                    continue
                to_login.append(status)
                break

    for status in to_logout:
        log_out_agent(
            primary_hostname,
            primary_token,
            status['tenant_uuid'],
            status['id'],
        )

    for status in to_login:
        log_in_agent(
            primary_hostname,
            primary_token,
            status['tenant_uuid'],
            status['id'],
            status['context'],
            status['extension'],
        )


if __name__ == '__main__':
    main()
