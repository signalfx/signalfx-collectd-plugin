#!/usr/bin/python

import json
import fcntl
import array
import struct
import socket
import subprocess
import sys
import string

import requests

import collectd

PLUGIN_NAME = 'signalfx-metadata'
METADATA_HASH = ""
METADATA = {}
API_TOKEN = ""
TIMEOUT = 10
POST_URL = "https://ingest.signalfx.com/v1/collectd"
VERSION = "0.0.1"
NOTIFY_LEVEL = -1
TYPE_INSTANCE = "host-meta-data"
TYPE = "objects"

# popen being used instead of subprocess to keep backward compatibility with python2.6
def popen(command):
    output = subprocess.Popen(command, stdout=subprocess.PIPE).communicate()[0]
    return string.strip(output)


def putval(pname, metric, val):
    collectd.Values(plugin=PLUGIN_NAME,
                    plugin_instance=pname,
                    meta={'0': True},
                    type=val[1].lower(),
                    type_instance=metric,
                    values=[val[0]]).dispatch()


def putnotif(property_name, message):
    notif = collectd.Notification(plugin=PLUGIN_NAME,
                                  plugin_instance=property_name,
                                  type_instance=TYPE_INSTANCE,
                                  type=TYPE)
    notif.severity = 4  # OKAY
    notif.message = message
    notif.dispatch()


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


def plugin_config(conf):
    for kv in conf.children:
        if kv.key == 'Notifications':
            if str2bool(kv.values[0]):
                collectd.register_notification(receive_notifications)
        elif kv.key == 'URL':
            global POST_URL
            POST_URL = kv.values[0]
        elif kv.key == 'Token':
            global API_TOKEN
            API_TOKEN = kv.values[0]
        elif kv.key == 'Timeout':
            global TIMEOUT
            TIMEOUT = int(kv.values[0])
        elif kv.key == 'NotifyLevel':
            global NOTIFY_LEVEL
            if string.lower(kv.values[0]) == "okay":
                NOTIFY_LEVEL = 4
            elif string.lower(kv.values[0]) == "warning":
                NOTIFY_LEVEL = 2
            elif string.lower(kv.values[0]) == "failure":
                NOTIFY_LEVEL = 1
            print NOTIFY_LEVEL
        else:
            raise Exception("unknown config parameter '%s'" % kv.key)


def send():
    send_notifications()


def write_notifications(host_info):
    for property_name, property_value in host_info.iteritems():
        putnotif(property_name, property_value)


# source http://code.activestate.com/recipes/439093-get-names-of-all-up-network-interfaces-linux-only/#c7
# trying not to bundle too much code along with this but this was the best, most portable version of what
# i needed
def all_interfaces():
    is_64bits = sys.maxsize > 2 ** 32
    struct_size = 40 if is_64bits else 32
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    max_possible = 8  # initial value
    while True:
        bytes = max_possible * struct_size
        names = array.array('B', '\0' * bytes)
        outbytes = struct.unpack('iL', fcntl.ioctl(
            s.fileno(),
            0x8912,  # SIOCGIFCONF
            struct.pack('iL', bytes, names.buffer_info()[0])
        ))[0]
        if outbytes == bytes:
            max_possible *= 2
        else:
            break
    namestr = names.tostring()
    return [(namestr[i:i + 16].split('\0', 1)[0],
             socket.inet_ntoa(namestr[i + 20:i + 24]))
            for i in range(0, outbytes, struct_size)]


def get_interfaces(host_info={}):
    for interface, ipaddress in all_interfaces():
        if ipaddress == "127.0.0.1":
            continue
        host_info["ipaddress_" + interface] = ipaddress
        host_info["fqdn_" + interface] = socket.gethostbyaddr(ipaddress)[0]
    return host_info


def get_cpu_info(host_info={}):
    info_raw = popen(["cat", "/proc/cpuinfo"])
    model = ""
    nb_cpu = 0
    nb_cores = 0
    nb_units = 0
    for p in string.split(info_raw, "\n"):
        if ':' in p:
            x, y = map(lambda x: string.strip(x), string.split(p, ':', 1))
            if x.startswith("physical id"):
                if nb_cpu < int(y):
                    nb_cpu = int(y)
            if x.startswith("cpu cores"):
                if nb_cores < int(y):
                    nb_cores = int(y)
            if x.startswith("processor"):
                if nb_units < int(y):
                    nb_units = int(y)
            if x.startswith("model name"):
                model = y

    nb_cpu += 1
    nb_units += 1
    host_info["cpu_model"] = model
    host_info["physical_cpus"] = str(nb_cpu)
    host_info["cpu_cores"] = str(nb_cores)
    host_info["logical_cpus"] = str(nb_units)
    return host_info


# platform module throws exceptions while running within the python collectd plugin
# shell out to uname instead
def get_kernel_info(host_info={}):
    host_info["kernel_name"] = popen(["uname", "-s"])
    host_info["kernel_release"] = popen(["uname", "-r"])
    host_info["kernel_version"] = popen(["uname", "-v"])
    host_info["machine"] = popen(["uname", "-m"])
    host_info["processor"] = popen(["uname", "-p"])
    host_info["operating_system"] = popen(["uname", "-o"])
    return host_info


def get_aws(thing, host_info={}):
    try:
        r = requests.get("http://169.254.169.254/latest/meta-data/%s" % thing, timeout=0.1)
        if r.ok:
            host_info["aws_%s" % thing.replace('-', '_')] = r.text
    except:
        pass  # no biggie, probably not on aws


def get_aws_info(host_info={}):
    get_aws("instance-id", host_info)
    get_aws("instance-type", host_info)
    get_aws("ami-id", host_info)
    get_aws("mac", host_info)
    get_aws("reservation-id", host_info)
    get_aws("profile", host_info)


def get_host_info():
    host_info = get_interfaces({})
    get_cpu_info(host_info)
    get_kernel_info(host_info)
    get_aws_info(host_info)
    host_info["metadata_version"] = VERSION
    return host_info


def mapdiff(host_info, old_host_info):
    diff = {}
    for k, v in host_info.iteritems():
        if not old_host_info.has_key(k):
            diff[k] = v
        elif old_host_info[k] != v:
            diff[k] = v
    return diff


def write_datapoint():
    putval("ping", "host-meta-data", [0, "gauge"])


def send_notifications():
    global METADATA_HASH
    global METADATA
    host_info = get_host_info()
    host_hash = hash(frozenset(host_info.items()))
    old_host_info = METADATA
    METADATA = host_info
    if METADATA_HASH != host_hash:
        METADATA_HASH = host_hash
        if old_host_info != {}:
            host_info = mapdiff(host_info, old_host_info)

        write_datapoint()
        write_notifications(host_info)


def get_severity(severity_int):
    return {
        1: "FAILURE",
        2: "WARNING",
        4: "OKAY"
    }[severity_int]


def receive_notifications(notif):
    notif_dict = {}
    # because collectd c->python is a bit limited and lacks __dict__
    for x in ['host', 'message', 'plugin', 'plugin_instance', 'severity', 'time', 'type',
              'type_instance']:
        notif_dict[x] = notif.__getattribute__(x)

    # emit notifications that are ours, or satisfy the notify level
    if notif_dict['plugin'] != PLUGIN_NAME and \
                    notif_dict['type'] != TYPE and \
                    notif_dict['type_instance'] != TYPE_INSTANCE and \
                    notif_dict["severity"] > NOTIFY_LEVEL:
        print notif_dict
        return

    notif_dict["severity"] = get_severity(notif_dict["severity"])
    payload = json.dumps([notif_dict])
    headers = {"Content-Type": "application/json"}
    if API_TOKEN != "":
        headers["X-SF-TOKEN"] = API_TOKEN
    r = requests.post(POST_URL, data=payload, headers=headers, timeout=TIMEOUT)
    sys.stdout.write(string.strip(r.text))


collectd.register_config(plugin_config)
collectd.register_read(send)
