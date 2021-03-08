# ipmi-check-temperature

Simple python script that attempts to check the ambient room temperature (via ipmitools) and send email notification if the temperature exceeds a maximum.

## What this does

- parse `ipmitool sdr` to get the ambient temperature
- keep a record of all readings
- send a notification if the current temperature is over the maximum
- ensure only one notification is sent in a given period (cooldown)

## Why you probably do NOT want use this script

This script is only on GitHub to make my life easier - there are many reasons why you should not use it.

- it needs to be run as root (and you shouldn't be running random scripts as root)
- there are almost certainly much better tested tools that exist already
- it has been only been tested on a very limited set of machines
- you may need to configure your smtp server to get emails work

## Why you might want to use this script

- You already have an excellent monitoring system in place
- You have looked at every line of code and are completely happy running this on your system
- You want a simple script to act as a last resort record keeper and failover notification server
- You have confirmed that the email notifications are working on your system (see below)

## Requirements

```
yum install OpenIPMI ipmitools
```

## Run

This script is intended to be run in the root crontab. It will direct all info messages (and above) to STDOUT and all warnings (and above) to STDERR, so a typical cron entry might look like:

```
*/5 * * * * /usr/bin/python3 ipmi-check-temperature.py --maxtemp 25 --email name1@server.com >> /dev/null
```

All temperature readings are stored in a log file (default: `/var/log/ipmi-check-temperature.log`)

```
$ tail -f /var/log/ipmi-check-temperature.log
2021-03-08 23:25:36.901939      14      17      -       -       -
2021-03-08 23:25:50.701302      15      17      -       -       -
2021-03-08 23:26:04.174605      16      17      -       -       -
2021-03-08 23:26:35.988814      18      17      WARNING NOTIFY  -
2021-03-08 23:40:19.698883      19      17      WARNING NO_NOTIFY_COOLDOWN      480
2021-03-08 23:40:36.124472      19      17      WARNING NO_NOTIFY_COOLDOWN      463
```

Simple usage: 

```
$ sudo python3 ipmi-check-temperature.py --maxtemp 25
2021-03-08 22:48:19,366 | INFO | Current temp is 16 (max 25)   [OKAY]
```

Simulating an overheating event (without email)

```
$ sudo python3 ipmi-check-temperature.py --maxtemp 10
2021-03-08 22:52:07,075 | INFO | Current temp is 16 (max 10)   [WARNING]
2021-03-08 22:52:07,078 | INFO | Warning state: NOT sending notification (no notify emails specified)
```

Similating an overheating event (test email notification)

```
$ sudo python3 ipmi-check-temperature.py --maxtemp 10 --email name1@server.com --email name2@server.com
2021-03-08 22:53:46,418 | INFO | Current temp is 16 (max 10)   [WARNING]
2021-03-08 22:53:46,420 | INFO | Warning state: sending notification
2021-03-08 22:53:46,452 | INFO | Sending notification to ['name1@server.com', 'name2@server.com']
2021-03-08 22:53:46,603 | INFO | Touching notify file /tmp/ipmi-check-temperature.last-notification.txt
```

Similating an overheating event (test 'cooldown' period)

```
$ sudo python3 ipmi-check-temperature.py --maxtemp 10 --email name1@server.com --email name2@server.com
2021-03-08 22:55:30,074 | INFO | Current temp is 15 (max 10)   [WARNING]
2021-03-08 22:55:30,076 | INFO | Warning state: NOT sending notification (waiting 496s for timeout)
```
