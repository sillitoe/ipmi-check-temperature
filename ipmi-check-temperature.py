#!/usr/bin/env python3

import argparse
import datetime
import getpass
import logging
import pathlib
import platform
import re
import smtplib
import ssl
import subprocess
import sys
import tempfile

from email.message import EmailMessage

LOG = None
LOG_FORMAT = '%(asctime)s | %(levelname)s | %(message)s'

DEFAULT_MAX_TEMP = 25
DEFAULT_LOG_FILE = '/var/log/ipmi-check-temperature.log'
DEFAULT_LASTNOTIFY_FILE = '/tmp/ipmi-check-temperature.last-notification.txt'
DEFAULT_LASTNOTIFY_COOLDOWN = 60 * 10 # send max of 1 email every 10 mins
IPMI_SDR_PREFIXES = [
    'Inlet Temp',
    'Ambient Temp',
]

SMTP_PORT = 465
EMAIL_HOST = 'localhost'
EMAIL_SUBJECT = "Temperature {current_temp} exceeds max (host: {hostname})"
EMAIL_FROM = "{username}@{hostname}"
EMAIL_TEMPLATE = """

WARNING: temperature on host {hostname} is currently at {current_temp}C which is 
greater than the maximum temperature ({max_temp}C). 

Last few lines of temperature log:

{last_log_lines}

"""


ACTION_SEND_NOTIFICATION = "NOTIFY"
ACTION_NO_NOTIFICATION_MISSING_EMAIL = "NO_NOTIFY_MISSING_EMAIL"
ACTION_NO_NOTIFICATION_COOLDOWN = "NO_NOTIFY_COOLDOWN"


parser = argparse.ArgumentParser(description='Check ambient temperature on this machine')
parser.add_argument('--maxtemp', dest='max_temp', type=int, default=DEFAULT_MAX_TEMP,
                    help=f'maximum temperature before sending notification (default: {DEFAULT_MAX_TEMP})')
parser.add_argument('--log', dest='log_file', type=str, default=DEFAULT_LOG_FILE,
                    help=f'log file to record temperatures (default: {DEFAULT_LOG_FILE})')
parser.add_argument('--email', dest='notify_emails', type=str, action='append',
                    help=f'email address(es) to send notification')
parser.add_argument('--cooldown', dest='notify_cooldown', type=int, default=DEFAULT_LASTNOTIFY_COOLDOWN,
                    help=f'second to wait before sending another notification (default: {DEFAULT_LASTNOTIFY_COOLDOWN})')
parser.add_argument('--notifyfile', dest='notify_file', type=str, default=DEFAULT_LASTNOTIFY_FILE,
                    help=f'file to record the last notification (default: {DEFAULT_LASTNOTIFY_FILE})')


def run(*, max_temp, log_file, notify_file, notify_cooldown, notify_emails):
    """Checks temperature and sends notification if necessary"""

    current_temp = get_temperature()

    warning_state = False
    if current_temp > max_temp:
        warning_state = True

    LOG.info("Current temp is {} (max {})   [{}]".format(
        current_temp, max_temp, "WARNING" if warning_state else "OKAY"))

    last_notification = get_last_notification(notify_file)
    except IOError as err:
        LOG.warning(f"Caught IOError when getting last notification: {err}")
        pass

    now = datetime.datetime.now()
    seconds_until_next_notification = notify_cooldown - (now.timestamp() - last_notification)
    
    action = None
    if warning_state:
        if seconds_until_next_notification < 0:
            if notify_emails:
                LOG.info(f"Warning state: sending notification")
                action = ACTION_SEND_NOTIFICATION
            else:
                LOG.info(f"Warning state: NOT sending notification (no notify emails specified)")
                action = ACTION_NO_NOTIFICATION_MISSING_EMAIL
        else:
            LOG.info(f"Warning state: NOT sending notification (waiting {int(seconds_until_next_notification)}s for cooldown)")
            action = ACTION_NO_NOTIFICATION_COOLDOWN

    if action == ACTION_SEND_NOTIFICATION:
        send_email_notification(log_file=log_file, 
                                notify_file=notify_file, 
                                notify_emails=notify_emails, 
                                current_temp=current_temp, 
                                max_temp=max_temp)

    log_cols = [str(now),
                str(current_temp), 
                str(max_temp), 
                "WARNING" if warning_state else '-',
                action if action is not None else '-',
                str(int(seconds_until_next_notification)) if action == ACTION_NO_NOTIFICATION_COOLDOWN else '-',]

    with open(args.log_file, 'at') as fh:
        fh.write('\t'.join(log_cols) + "\n")





def send_email_notification(*, log_file, notify_file, notify_emails, current_temp, max_temp):
    """Sends email notification"""

    tmpl_args = {
        'hostname': platform.node(),
        'username': getpass.getuser(),
        'current_temp': current_temp,
        'max_temp': max_temp,
        'last_log_lines': get_last_lines(log_file),
    }

    email_content = EMAIL_TEMPLATE.format(**tmpl_args)

    msg = EmailMessage()

    msg.set_content(email_content)
    msg['Subject'] = EMAIL_SUBJECT.format(**tmpl_args)
    msg['From'] = EMAIL_FROM.format(**tmpl_args)
    msg['To'] = ', '.join(notify_emails)

    LOG.info(f"Sending notification to {notify_emails}")
    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.send_message(msg)

    LOG.info(f"Touching notify file {notify_file}")
    pathlib.Path(notify_file).touch()


def get_temperature():
    """
    Returns the temperature from `ipmitool sdr`

    ::

    $ sudo ipmitool sdr  | grep -i 'inlet temp'
    Inlet Temp       | 21 degrees C      | ok
    
    """

    try:
        result = subprocess.run(['ipmitool', 'sdr'], 
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8', check=True)
    except Exception as err:
        msg = f"failed to run ipmitool: OUT: {err.stdout} ERR:{err.stderr}"
        LOG.error(msg)
        raise

    temp = None
    for line in result.stdout.splitlines():
        if not any([line.startswith(prefix) for prefix in IPMI_SDR_PREFIXES]):
            continue
        
        line = line.strip()
        name, value, status = line.split('|')
        value = value.strip()
        
        if value == 'disabled':
            continue
        
        match = re.match(r'(\d+) degrees C', value)

        if not match:
            msg = f"failed to parse temperature from '{value}' (line: {line})"
            raise RuntimeError(msg)

        temp = match.group(1)
        break
    
    if temp is None:
        msg = f"failed to find line '{IPMI_SDR_PREFIX}' in output of `ipmitool sdr`"
        raise RuntimeError(msg)

    return int(temp)

def get_last_notification(notify_file):
    """Returns when the last notification was sent (sec since epoch)"""

    try:
        notify_path = pathlib.Path(notify_file)
        return notify_path.stat().st_mtime
    except IOError:
        return 0


def get_last_lines(log_file, line_count=5):
    """Gets the last few lines of the log file"""

    result = subprocess.run(['tail', '-n', str(line_count), str(log_file)],
            check=True, encoding='utf-8', stdout=subprocess.PIPE)

    return result.stdout.splitlines()


def setup_logger():
    """Logs >= INFO to stdout; >= WARNING to stderr"""
 
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setLevel(logging.WARNING)

    formatter = logging.Formatter(LOG_FORMAT)

    stdout_handler.setFormatter(formatter)
    stderr_handler.setFormatter(formatter)

    logger.addHandler(stdout_handler)
    logger.addHandler(stderr_handler)

    return logger


if __name__ == '__main__':
    LOG = setup_logger()
    args = parser.parse_args()
    run(**(args.__dict__))



