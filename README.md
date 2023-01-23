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

* The primary should have it's HA configured as master
* The secondary should have it's HA configured as disabled
* Manually configure the slave to allow PG synchronization

In `/etc/postgresql/11/main/pg_hba.conf` add the following line replacing
`<PRIMARY IP ADDRESS>` with the IP address of the primary Wazo.
```
host asterisk postgres <PRIMARY IP ADDRESS>/32 trust
```

* Setup SSH key authorization between master and slave

Launch `xivo-sync -i` on the primary

### Add a cron to check the state of the primary on the Kamailio proxy

Copy the `bin/wazo-ha-check` script to `/usr/sbin/wazo-ha-check`

Add the following content to `/etc/cron.d/wazo-active-active-ha`

```
* * * * * root /usr/sbin/wazo-ha-check <PRIMARY IP ADDRESS> >/dev/null
```

## Voicemail synchronization

* Install nfs server on the somewhere in your infrastructure.

I installed it on the same VM as my Kamailio using the following command

```
dnf install nfs-utils
```

* Start the nfs server

```
systemctl enable nfs-server.service
systemctl start nfs-server.service
```

* Create the directory for voicemails

```
mkdir -p /mnt/nfs_shares/voicemails
```

* Add the created directory to nfs exports in `/etc/exports` by adding the following line replacing `<PRIMARY IP ADDRESS>` and `<SECONDARY IP ADDRESS>`

```
/mnt/nfs_shares/voicemails	<PRIMARY IP ADDRESS>(rw,no_root_squash,sync) <SECONDARY IP ADDRESS>(rw,no_root_squash,sync)
```

* Export the directory

```
exportfs -arv
```

* If you are using `firewalld` it will need to be configured for nfs

```
firewall-cmd --permanent --add-service=nfs
firewall-cmd --permanent --add-service=rpc-bind
firewall-cmd --permanent --add-service=mountd
firewall-cmd --reload
```

* Install the nfs client on each Wazo stack

```
apt update
apt install nfs-common nfs4-acl-tools
```

* Test to see if the exports are visible

```
showmount -e <NFS SERVER IP address>
```

The output should be similar to this

```
Export list for <proxy IP address>:
/mnt/nfs_shares/voicemails <Wazo primary IP address>,<Wazo secondary IP address>
```
        
* Create the local voicemail directory

```
mv /var/spool/asterisk/voicemail /var/spool/asterisk/voicemail_old
mkdir /var/spool/asterisk/voicemail
mount -t nfs <NFS SERVER IP ADDRESS>:/mnt/nfs_shares/voicemails /var/spool/asterisk/voicemail
```

* Copy old voicemails to the nfs share

```
mv -i /var/spool/asterisk/voicemail_old/* /var/spool/asterisk/voicemail
rmdir /var/spool/asterisk/voicemail_old
```

* Make the nfs mount permanent 

```
echo "<NFS SERVER IP ADDRESS>:/mnt/nfs_shares/voicemails /var/spool/asterisk/voicemail nfs defaults 0 0">>/etc/fstab
```

## CEL replication

Asterisk CEL are inserted on both Wazo stacks and the call logs are generated
on both stacks.

### Configuring the primary

* Add the following lines to `/etc/odbc.ini`

```
[secondary]
Description=Connection to the database of the secondary Wazo
Driver=PostgreSQL ANSI
Trace=No
Database=asterisk
Servername=<SECONDARY IP ADDRESS>
```

* Create the matching `res_odbc` config in `/etc/asterisk/res_odbc.d/02-active-active.conf`

```
[secondary]
enabled => yes
dsn => secondary
username => asterisk
password => proformatique
pre-connect => yes
max_connections => 1
```

* Enable CEL logging on the secondary ODBC connection in `/etc/asterisk/cel_odbc.d/02-active-active.conf`

```
[secondary]
connection = secondary
table = cel
```

* Configure Postgresql to allow ODBC connection from the secondary in `/etc/postgresql/11/main/pg_hba.conf` add

```
hostnossl asterisk asterisk <SECONDARY IP ADDRESS>/32 md5
```

### Configuring the secondary

* Add the following lines to `/etc/odbc.ini`

```
[primary]
Description=Connection to the database of the primary Wazo
Driver=PostgreSQL ANSI
Trace=No
Database=asterisk
Servername=<PRIMARY IP ADDRESS>
```

* Create the matching `res_odbc` config in `/etc/asterisk/res_odbc.d/02-active-active.conf`

```
[primary]
enabled => yes
dsn => primary
username => asterisk
password => proformatique
pre-connect => yes
max_connections => 1
```

* Enable CEL logging on the primary ODBC connection in `/etc/asterisk/cel_odbc.d/02-active-active.conf`

```
[primary]
connection = primary
table = cel
```

* Configure Postgresql to allow ODBC connection from the secondary in `/etc/postgresql/11/main/pg_hba.conf` add

```
hostnossl asterisk asterisk <PRIMARY IP ADDRESS>/32 md5
```

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

2. Stop the HA check cron from the proxy

    Stop automatic traffic switching from the HA cron

3. Do one last manual synchronization

    This will synchronize all changes made in the last hours before upgrading

4. Generate call logs

    Avoid a big gap in the call logs by forcing the call log generation for calls that happenned on the other Wazo

5. wazo-upgrade the secondary

    Check for errors

6. Switch mode to "maintenance" from the proxy

7. Monitor calls on the primary until all calls are on the secondary

    Wait until all calls are done on the primary before upgrading, the upgrade will stop services

8. wazo-upgrade the primary

    Check for errors

9. Switch mode to "normal" from the proxy

10. Restart the synchronization cron on the primary

    All done
