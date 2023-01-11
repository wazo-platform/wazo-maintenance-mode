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

## HA configuration

The primary should have it's HA configured as master
The secondary should have it's HA configured as disabled
Manually configure the slave to allow PG synchronization
launch xivo-sync -i on the master


## BLF synchronization

The file `etc/asterisk/pjsip.d/06-active-active.conf.sample` needs to be copied to
`/etc/asterisk/pjsip.d/06-active-active.conf` on each Wazo stacks.

The content of the file should be modified as follow

On the primary

Change `<OTHER IP ADDRESS>` to the IP address of the secondary

On the secondary

Change `<OTHER IP ADDRESS>` to the IP address of the primary
Change all occurences of `instance2` to `instance1`

# Current limitations


# Upgrading

0. Create a snapshot of the primary and secondary

    If the secondary fails to upgrade save the logs and revert to the snapshot
    If the primary fails to upgrade save the logs and revert the master to its snapsnot, then switch back to normal mode, once all calls are back on the primary restore the secondary from its snapshot

1. Stop the synchronization cron on the primary

    This prevents a DB synchronization from happening when the Wazo stacks
    are not in the same version and could have different database schema.

2. Do one last manual synchronization

    This will synchronize all changes made in the last hours before upgrading

3. Generate call logs

    Avoid a big gap in the call logs by forcing the call log generation for calls that happenned on the other Wazo

4. wazo-upgrade the secondary

    Check for errors

5. Switch mode to "maintenance" from the proxy

6. Monitor calls on the primary until all calls are on the secondary

    Wait until all calls are done on the primary before upgrading, the upgrade will stop services

7. wazo-upgrade the primary

    Check for errors

8. Switch mode to "normal" from the proxy

9. Restart the synchronization cron on the primary

    All done
