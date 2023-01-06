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

# Current limitations

## BLF

Since only one of the Asterisk recieves a SUBSCRIBE there are only one Asterisk updating BLF
