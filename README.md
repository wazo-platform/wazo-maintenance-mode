# wazo-maintenance-mode
Tools to upgrade a Wazo stack without service interruption

# Infrastructure

The goal of this repository is to document and collect tools required
to be able to upgrade a Wazo stack without interruptions.

Your infrastructure will require the following.

2 Wazo stacks configured in HA mode
1 server with Kamailio installed

The kamailio server should have to hostnames pointing to it's IP address.

The Kamailio server named "proxy" from now on should be able to ssh to both Wazo stacks without entering a password

On the proxy execute the following commands

```
ssh-keygen -t ed25519
ssh-copy-id root@<primary-stack-hostname>
ssh-copy-id root@<secondary-stack-hostname>
```

# Configuration

BLF synchronization

The file `etc/asterisk/pjsip.d/06-active-active.conf.sample` needs to be copied to
`/etc/asterisk/pjsip.d/06-active-active.conf` on each Wazo stacks.

The content of the file should be modified as follow

On the primary

Change `<OTHER IP ADDRESS>` to the IP address of the secondary

On the secondary

Change `<OTHER IP ADDRESS>` to the IP address of the primary
Change all occurences of `instance2` to `instance1`

# Current limitations
