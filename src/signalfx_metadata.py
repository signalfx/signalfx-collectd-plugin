#!/usr/bin/python

import array
import binascii
import copy
import fcntl
import os
import os.path
import platform
import random
import re
import signal
import socket
import string
import struct
import subprocess
import sys
import threading
import time
import zlib
from urlparse import urlparse

import psutil

import collectd_dogstatsd

PLUGIN_UPTIME = "sf.host-plugin_uptime"

try:
    import urllib.request as urllib2
except ImportError:
    import urllib2

try:
    import json
except ImportError:
    import simplejson as json

try:
    str.decode("ami3?")
    bytes = str
except:
    pass

try:
    import collectd
    import logging

    logging.basicConfig(level=logging.INFO)
except ImportError:
    try:
        import dummy_collectd as collectd
    except:
        pass

if sys.platform == 'darwin':
    try:
        from netifaces import interfaces, ifaddresses, AF_INET
    except:
        pass

PLUGIN_NAME = 'signalfx-metadata'
API_TOKENS = []
TIMEOUT = 3
POST_URLS = []
DEFAULT_POST_URL = "https://ingest.signalfx.com/v1/collectd"
VERSION = "0.0.32"
MAX_LENGTH = 0
COLLECTD_VERSION = ""
SIGNALFX_AGENT_VERSION = ""
LINUX_VERSION = ""
NOTIFY_LEVEL = -1
HOST_TYPE_INSTANCE = "host-meta-data"
TOP_TYPE_INSTANCE = "top-info"
TYPE = "objects"
HOST_METADATA = True


def DEFAULT_NEXT_METADATA_SEND():
    """returns the default next metadata send"""
    return 0


NEXT_METADATA_SEND = DEFAULT_NEXT_METADATA_SEND()
NEXT_METADATA_SEND_KEY = "NEXT_METADATA_SEND"


def DEFAULT_NEXT_METADATA_SEND_INTERVAL():
    """returns the default next metadata send intervals"""
    return [random.randint(0, 60), 60,
            3600 + random.randint(0, 60),
            86400 + random.randint(0, 600)]


NEXT_METADATA_SEND_INTERVAL = DEFAULT_NEXT_METADATA_SEND_INTERVAL()
NEXT_METADATA_SEND_INTERVAL_KEY = "NEXT_METADATA_SEND_INTERVAL"
LAST = 0
AWS = False
AWS_SET = False
PROCESS_INFO = True
DATAPOINTS = True
UTILIZATION = True
INTERVAL = 10
HOST = ""
UP = time.time()
DEBUG = False
NOTIFICATIONS = False

RESPONSE_LOCK = threading.Lock()
METRIC_LOCK = threading.Lock()
MAX_RESPONSE = 0
RESPONSE_ERRORS = 0

DOGSTATSD_INSTANCE = collectd_dogstatsd.DogstatsDCollectD(collectd)
PERCORECPUUTIL = False
OVERALLCPUUTIL = True
ETC_PATH = "{0}etc".format(os.sep)
SAVED_HOST = None
SAVED_HOST_KEY = "SAVED_HOST"
PERSISTENCE_PATH = None
PERSISTENCE_FILE = "sfx_metadata_state.json"


class mdict(dict):
    """
    a dictionary class that has a skipped flag for missing data purposes.
    """

    def __init__(self, *args, **kw):
        super(mdict, self).__init__(*args, **kw)
        self.skipped = False


class Utilization(object):
    """
    Base class for all utilizations.
    """

    def __init__(self):
        self.metrics = {}
        self.last_time = 0
        self.interval = 0
        self.wait_threshold = 3

    def get_time(self, values_obj):
        return round(values_obj.time, 1)

    def write(self, values_obj):
        """
        checks if it is this utilization's metric and adds if so. determines
        the interval this data is appearing on.

        :param values_obj: python plugin Values object
        :return: None
        """
        if self.is_metric(values_obj):
            self.add_metric(values_obj)
            if not self.interval:
                self.interval = values_obj.interval
                if not self.interval:
                    self.interval = INTERVAL
            return True
        return False

    def add_metric(self, values_obj):
        """
        create a name, round the time to nearest 10th of a second due to not
        perfect timings for disk and network.

        :param values_obj: python plugin Values object
        :return: None
        """
        metric = values_obj.type
        if values_obj.type_instance:
            metric += "." + values_obj.type_instance
        ti = self.get_time(values_obj)
        metric_time = self.metrics.setdefault(ti, mdict())
        metric_time[metric] = values_obj.values

    def emit_utilization(self, t, used, total, metric,
                         plugin_instance="utilization", obj=None, dims=None):
        """
        emit a utilization metric

        :param t: time to emit, default is 0.0 meaning now
        :param used: how much has been used
        :param total: total amount
        :param metric: metric to be emitted as
        :param plugin_instance:  plugin_instance to be emitted as
        :param obj: debug passthrough
        :return: the percent calculated, a number
        """
        if total == 0:
            percent = 0
        else:
            percent = 1.0 * used / total * 100
        if dims is not None:
            plugin_instance += '[{dims}]'.format(dims=','.join(['='.join(d)
                                                 for d in dims.items()]))
        if percent < 0:
            log("percent <= 0 %s %s %s %s %s" %
                (used, total, metric, plugin_instance, obj))
            return percent
        if percent > 100:
            log("percent > 100 %s %s %s %s %s" %
                (used, total, metric, plugin_instance, obj))
            return percent
        if t < self.last_time:
            debug("too old %s %s %s %s" % (t, metric, percent, self.last_time))
        else:
            put_val(plugin_instance, "", [percent, metric], t=t,
                    i=self.interval)
            self.last_time = t
            debug("%s %s %s" % (t, metric, percent))
        return percent


class PluginInstanceUtilization(Utilization):
    """
    A utilization base class for things that are on a per-plugin_instance
    basis.
    """

    def __init__(self):
        Utilization.__init__(self)

    def add_metric(self, values_obj):
        """
        Almost exactly like Utilization.add_metric except takes into account
        plugin_instance.

        :param values_obj: python plugin Values object
        :return: None
        """
        metric = values_obj.type
        if values_obj.type_instance:
            metric += "." + values_obj.type_instance
        ti = self.get_time(values_obj)
        metric_time = self.metrics.setdefault(ti, mdict())
        metric_plugin_instance = metric_time.setdefault(
            values_obj.plugin_instance, mdict())
        metric_plugin_instance[metric] = values_obj.values


class DfUtilization(PluginInstanceUtilization):
    """
    DfUtilization gives a 0 <= gauge <= 100 of the overall utilization of the
    partition for each partition.
    """

    def __init__(self):
        PluginInstanceUtilization.__init__(self)

    def is_metric(self, values_obj):
        return values_obj.plugin == "df" and values_obj.type == "df_complex"

    def read(self):
        """
        emit df utilization metrics on a per partition basis

        :return: None
        """
        for t in sorted(self.metrics.keys()):
            # check if metric is too old
            if t > self.last_time:
                for plugin_instance in self.metrics[t].keys():
                    m = self.metrics[t][plugin_instance]
                    if len(m) == 3:
                        used = m["df_complex.used"][0]
                        free = m["df_complex.free"][0]
                        total = used + free
                        self.emit_utilization(t, used, total,
                                              "disk.utilization",
                                              plugin_instance, obj=m)
                        del (self.metrics[t][plugin_instance])
                    else:
                        # skip em once to give metrics time to arrive
                        if m.skipped:
                            debug("incomplete metric %s %s %s" %
                                  (plugin_instance, t, m))
                            del (self.metrics[t][plugin_instance])
                        else:
                            m.skipped = True
            else:
                debug("too old %s %s" % (t, self.metrics[t].keys()))
                self.metrics[t] = None
            if not self.metrics[t]:
                del (self.metrics[t])


class MemoryUtilization(Utilization):
    """
    MemoryUtilization gives a 0 <= gauge <= 100 of the overall utilization of
    memory
    """

    def __init__(self):
        Utilization.__init__(self)
        self.size = 0

    def is_metric(self, values_obj):
        return values_obj.plugin == "memory" and values_obj.type == "memory"

    def read(self):
        """
        emit memory utilization metrics.  different collectds send in
        different #s of metrics so wait "self.wait_threshold" intervals to
        figure out which.

        :return: None
        """
        if self.size == 0:
            if len(self.metrics) >= self.wait_threshold:
                self.size = max(map(len, self.metrics.values()))
            else:
                return

        for t in sorted(self.metrics.keys()):
            if t > self.last_time:
                m = self.metrics[t]
                if len(m) == self.size:
                    total = sum(c[0] for c in m.values())
                    used = 0
                    if sys.platform == 'darwin':
                        used = m["memory.active"][0] + m["memory.wired"][0]
                    else:
                        used = m["memory.used"][0]

                    self.emit_utilization(t, used, total,
                                          "memory.utilization", obj=m)
                else:
                    debug("incomplete metric %s %s" % (t, self.metrics[t]))
            else:
                debug("too old %s %s" % (t, self.metrics[t].keys()))
                self.metrics[t] = None
            del (self.metrics[t])


class CpuUtilizationCalculator():

    def __init__(self, core):
        self.core = core
        self.last = {}
        self.old_total = 0
        self.old_idle = 0
        self.old_used = 0

    def calculateUtilization(self, t, metric):
        """
        Calculate cpu utilization metric
        :return: (t, used_diff, total_diff) or None
        """

        response = None
        self.last.update(metric)
        total = sum(c[0] for c in self.last.values())
        idle = self.last.get("cpu.idle", [0])[0]
        used = total - idle
        if self.old_total != 0:
            used_diff = used - self.old_used
            total_diff = total - self.old_total
            if used_diff < 0 or total_diff < 0:
                log("t %s used %s total %s old used %s old total %s" %
                    (t, used, total, self.old_used, self.old_total))
            elif used_diff == 0 and total_diff == 0:
                log("zeros %s %s" % (self.last, metric))
            else:
                response = (t, used_diff, total_diff)
        self.old_total = total
        self.old_idle = idle
        self.old_used = used
        return response


class CpuUtilizationPerCore(PluginInstanceUtilization):
    """
    CpuUtilization gives a 0 <=gauge <=100 of the overall utilization of each
    cpu core.
    """
    def __init__(self):
        PluginInstanceUtilization.__init__(self)
        self.cores = {}

    def is_metric(self, values_obj):
        return (values_obj.plugin == "cpu")

    def read(self):
        """"
        emit cpu utilization metric when we've seen all the cpu aggregation
        metrics we need.  Have to watch out for incomplete metrics.

        :return: None
        """
        if PERCORECPUUTIL is True:
            min_expected_metrics = 8
            if sys.platform == 'darwin':
                min_expected_metrics = 4
            for t in sorted(self.metrics.keys()):
                if t > self.last_time:
                    skip = False
                    # Iterate over all cpu's to check if all metrics are
                    # reported. Because we have to skip the whole metric
                    # containing information on both cores
                    for core in self.metrics[t].keys():
                        if len(self.metrics[t][core]) < min_expected_metrics:
                            skip = True
                    if skip:
                        # skip em once to give metrics time to arrive
                        if self.metrics[t].skipped:
                            debug("incomplete metric %s %s"
                                  % (t, self.metrics[t]))
                            del (self.metrics[t])
                        else:
                            self.metrics[t].skipped = True
                    # If the metric is not skipped,
                    # then proceed with calculation
                    else:
                        for core in self.metrics[t].keys():
                            # Add core to self.cores if necessary
                            if core not in self.cores.keys():
                                self.cores[core] = \
                                    CpuUtilizationCalculator(core)

                            response = self.cores[core].calculateUtilization(
                                t,
                                self.metrics[t][core]
                            )

                            if response is not None:
                                self.emit_utilization(
                                    *response,
                                    metric="cpu.utilization_per_core",
                                    obj=(t, self.metrics[t][core]),
                                    dims={"core": "cpu{0}".format(core)}
                                )
                        del (self.metrics[t])
                else:
                    debug("too old %s %s" % (t, self.metrics[t].keys()))
                    del (self.metrics[t])
        else:
            self.metrics = {}


class CpuUtilization(Utilization):
    """
    CpuUtilization gives a 0 <=gauge <=100 of the overall utilization of cpu.
    """

    def __init__(self):
        Utilization.__init__(self)
        self.util_calc = CpuUtilizationCalculator(0)

    def is_metric(self, values_obj):
        return (values_obj.plugin == "aggregation" and
                values_obj.type == "cpu" and
                values_obj.plugin_instance == "cpu-average")

    def read(self):
        """
        emit cpu utilization metric when we've seen all the cpu aggregation
        metrics we need.  Have to watch out for incomplete metrics.

        :return: None
        """
        min_expected_metrics = 8
        if sys.platform == 'darwin':
            min_expected_metrics = 4

        for t in sorted(self.metrics.keys()):
            if t > self.last_time:
                if len(self.metrics[t]) >= min_expected_metrics:
                    response = self.util_calc.calculateUtilization(
                        t,
                        self.metrics[t]
                    )
                    if response is not None:
                        self.emit_utilization(*response,
                                              metric="cpu.utilization",
                                              obj=(t, self.metrics[t]))
                    del (self.metrics[t])
                else:
                    # skip em once to give metrics time to arrive
                    if self.metrics[t].skipped:
                        debug("incomplete metric %s %s" % (t, self.metrics[t]))
                        del (self.metrics[t])
                    else:
                        self.metrics[t].skipped = True
            else:
                debug("too old %s %s" % (t, self.metrics[t].keys()))
                del (self.metrics[t])


class Total(PluginInstanceUtilization):
    """
    Total is the base class for all Totals.  Provides a total, previous,
    size and a set of plugin instances.
    """

    def __init__(self):
        PluginInstanceUtilization.__init__(self)
        self.totals = {}
        self.previous = {}
        self.size = 0
        self.current_plugin_instances = set()

    def emit_total(self, metric, t):
        """
        emit a total metric

        :param t: time to emit, default is 0.0 meaning now
        :param metric: metric to be emitted as
        :return: None
        """
        total = sum(self.totals.values())
        put_val("summation", "", [total, metric], t=t, i=self.interval)
        debug("%s %s %s" % (t, metric, total))
        self.last_time = t

    def check_threshold(self):
        """
        Threshold exists so that we wait a certain # of intervals to "see the
        world", then make decisions on what is reporting.

        :return: None
        """

        if self.size == 0:
            if len(self.metrics) >= self.wait_threshold:
                self.size = max(map(len, self.metrics.values()))
                for t in self.metrics.keys():
                    if len(self.metrics[t]) != self.size:
                        del (self.metrics[t])
                    else:
                        self.current_plugin_instances = set(
                            self.metrics[t].keys())
                return True
        else:
            return True

        return False

    def read(self):
        """
        Once the threshold has been checked iterate through intervals
        emitting a total. Because these are cumulative counters on we need to
        never go down even if something stops reporting, so we start with 0
        and only send in diffs.  If they stop reporting we keep that in the
        total.  If they wrap we make that the diff.

        :return: None
        """
        if not self.check_threshold():
            return

        for t in sorted(self.metrics.keys()):
            if t > self.last_time:
                m = self.metrics[t]
                if m.skipped or len(m) >= self.size:
                    if len(m) > self.size:
                        self.size = len(m)
                    prev = copy.copy(self.previous)
                    current = {}
                    for x, y in m.iteritems():
                        current[x] = sum(y[self.total_type])
                    diff = {}
                    for k in current:
                        if k in prev:
                            v = current[k] - prev[k]
                            if v < 0:
                                if t <= self.last_time:
                                    debug(
                                        "older metric, don't show wrapping t "
                                        "%s last %s" % (t, self.last_time))
                                    del (self.metrics[t])
                                    continue
                                debug("we've wrapped %s prev %s current %s" %
                                      (k, prev[k], current[k]))
                                v = current[k]
                            del (prev[k])
                        else:
                            v = 0
                        diff[k] = v

                    # we don't need to look at the ones that aren't showing up
                    # we have their last diff in the total, and if they ever
                    # register again we'll record that diff

                    for k in diff:
                        self.totals[k] = self.totals.setdefault(k, 0) + diff[k]
                        self.previous[k] = current[k]
                    self.emit_total(self.metric_name, t)
                    del (self.metrics[t])
                else:
                    m.skipped = True
            else:
                debug("too old %s %s" % (t, self.metrics[t].keys()))
                del (self.metrics[t])


class DfTotalUtilization(Total):
    """
    DfTotalUtilization emits "disk.summary_utilization" which is a gauge of
    the used_bytes/total_bytes across all partitions.
    """

    def __init__(self):
        Total.__init__(self)
        self.probation_plugin_instances = set()

    def is_metric(self, values_obj):
        return values_obj.plugin == "df" and values_obj.type == "df_complex"

    def read(self):
        """
        Because you can mount or umount disks, we need to keep an accurate view
        of which are reporting.  We have skipped to mark metrics that have
        missed an interval and then if they get skipped we move that partition
        to probation.  if they violate probation we stop listening for them
        and consider them unmounted.

        Similary, if we see a new partition, we start listening for it.
        :return:
        """
        if not self.check_threshold():
            return

        for t in sorted(self.metrics.keys()):
            if t > self.last_time:
                used_total = 0
                free_total = 0
                pm = self.metrics[t]
                delete = True
                emit = True
                current = set(pm.keys())
                if current >= self.current_plugin_instances:
                    if current > self.current_plugin_instances:
                        self.size = len(pm)
                        diff = set(pm.keys()) - self.current_plugin_instances
                        debug("updating current_plugin_instances with diff %s"
                              % diff)
                        self.current_plugin_instances = set(pm.keys())
                    for plugin_instance in self.current_plugin_instances:
                        m = self.metrics[t][plugin_instance]
                        if len(m) == 3:
                            used_total += m["df_complex.used"][0]
                            free_total += m["df_complex.free"][0]
                        else:
                            emit = False
                            # skip em once to give metrics time to arrive
                            if pm.skipped:
                                debug("incomplete metric %s %s %s" %
                                      (plugin_instance, t, pm))
                                break
                            else:
                                pm.skipped = True
                                delete = False
                else:
                    emit = False
                    if pm.skipped:
                        debug("incomplete metric %s %s" %
                              (t, pm))
                        skipped_plugin_instances = set(pm.keys())
                        difference = self.current_plugin_instances.difference(
                            skipped_plugin_instances)
                        for d in difference:
                            if d in self.probation_plugin_instances:
                                self.current_plugin_instances.remove(d)
                                self.size = len(self.current_plugin_instances)
                                debug(
                                    "probate plugin_instance removed %s size "
                                    "now %s" % (d, self.size))
                                self.probation_plugin_instances.remove(d)
                            else:
                                debug("setting probate plugin_instance %s" % d)
                                self.probation_plugin_instances.add(d)

                    else:
                        pm.skipped = True
                        delete = False

                if emit:
                    self.emit_utilization(t, used_total,
                                          used_total + free_total,
                                          "disk.summary_utilization", obj=pm)
                if delete:
                    del (self.metrics[t])
            else:
                debug("too old %s %s" % (t, self.metrics[t].keys()))
                del (self.metrics[t])


class NetworkTotal(Total):
    """
    NetworkTotal emits "network.total" which is a counter of the total bytes,
    both tx and rx of this machine across all interfaces.
    """

    def __init__(self):
        Total.__init__(self)
        self.total_type = "if_octets"
        self.metric_name = "network.total"

    def is_metric(self, values):
        return values.plugin == "interface" and values.type == "if_octets"


class DiskTotal(Total):
    """
    DiskTotal emits "disk_ops.total" which is a counter of the total iops
    of this machine across all disks.
    """

    def __init__(self):
        Total.__init__(self)
        self.total_type = "disk_ops"
        self.metric_name = "disk_ops.total"

    def is_metric(self, values_obj):
        return values_obj.plugin == "disk" and values_obj.type == "disk_ops"


class UtilizationFactory:
    """
    Utilization factory handles the reading and wring of metrics accross
    utilizations.
    """

    def __init__(self):
        self.utilizations = [CpuUtilization(), MemoryUtilization(),
                             DfUtilization(), NetworkTotal(), DiskTotal(),
                             DfTotalUtilization(), CpuUtilizationPerCore()]

    def write(self, values_obj):
        """
        write callback method.

        The write methods for each utilization are listening for metrics of
        the type they want.

        :param values_obj: collectd.python Values object
        :return: None
        """
        with METRIC_LOCK:
            for u in self.utilizations:
                try:
                    u.write(values_obj)
                except:
                    t, e = sys.exc_info()[:2]
                    log("utilization write error: %s" % str(e))

    def read(self):
        """
        Emit all utilizations, this is called at a frequency of 1 to send any
        metrics that may be collectd at any rate.  Most of these will be noops.

        :return: None
        """
        with METRIC_LOCK:
            for u in self.utilizations:
                try:
                    u.read()
                except:
                    t, e = sys.exc_info()[:2]
                    log("utilization read error: %s" % str(e))


UTILIZATION_INSTANCE = UtilizationFactory()


class LargeNotif:
    """
    Used because the Python plugin supplied notification does not provide
    us with enough space
    """
    host = ""
    message = ""
    plugin = PLUGIN_NAME
    plugin_instance = ""
    severity = 4
    time = 0
    type = TYPE
    type_instance = ""

    def __init__(self, message, type_instance="", plugin_instance=""):
        self.plugin_instance = plugin_instance
        self.type_instance = type_instance
        self.message = message
        self.host = HOST

    def __repr__(self):
        return 'PUTNOTIF %s/%s-%s/%s-%s %s' % (self.host, self.plugin,
                                               self.plugin_instance,
                                               self.type, self.type_instance,
                                               self.message)


def debug(param):
    """ debug messages and understand if we're in collectd or a program """
    if DEBUG:
        if __name__ != '__main__':
            collectd.info("%s: DEBUG %s" % (PLUGIN_NAME, param))
        else:
            sys.stderr.write("%s\n" % param)


def log(param):
    """ log messages and understand if we're in collectd or a program """
    if __name__ != '__main__':
        collectd.info("%s: %s" % (PLUGIN_NAME, param))
    else:
        sys.stderr.write("%s\n" % param)


def plugin_config(conf):
    """
    :param conf:
      https://collectd.org/documentation/manpages/collectd-python.5.shtml
      #config

    Parse the config object for config parameters
    """

    DOGSTATSD_INSTANCE.config.configure_callback(conf)

    global POST_URLS
    for kv in conf.children:
        if kv.key == 'Notifications':
            if kv.values[0]:
                global NOTIFICATIONS
                NOTIFICATIONS = kv.values[0]
        elif kv.key == 'ProcessInfo':
            global PROCESS_INFO
            PROCESS_INFO = kv.values[0]
        elif kv.key == 'Datapoints':
            global DATAPOINTS
            DATAPOINTS = kv.values[0]
        elif kv.key == 'Utilization':
            global UTILIZATION
            UTILIZATION = kv.values[0]
        elif kv.key == 'PerCoreCPUUtil':
            global PERCORECPUUTIL
            PERCORECPUUTIL = kv.values[0]
        elif kv.key == 'OverallCPUUtil':
            global OVERALLCPUUTIL
            OVERALLCPUUTIL = kv.values[0]
        elif kv.key == 'Verbose':
            global DEBUG
            DEBUG = kv.values[0]
            log('setting verbose to %s' % DEBUG)
        elif kv.key == 'URL':
            POST_URLS.extend(kv.values)
        elif kv.key == 'Token':
            global API_TOKEN
            API_TOKENS.extend(kv.values)
        elif kv.key == 'Timeout':
            global TIMEOUT
            TIMEOUT = int(kv.values[0])
        elif kv.key == 'Interval':
            global INTERVAL
            INTERVAL = int(kv.values[0])
        elif kv.key == 'NotifyLevel':
            global NOTIFY_LEVEL
            if string.lower(kv.values[0]) == "okay":
                NOTIFY_LEVEL = 4
            elif string.lower(kv.values[0]) == "warning":
                NOTIFY_LEVEL = 2
            elif string.lower(kv.values[0]) == "failure":
                NOTIFY_LEVEL = 1
        elif kv.key == 'ProcPath':
            psutil.PROCFS_PATH = kv.values[0]
            debug("Setting proc path to %s for psutil" % psutil.PROCFS_PATH)
        elif kv.key == 'EtcPath':
            global ETC_PATH
            ETC_PATH = kv.values[0].rstrip(os.pathsep).rstrip(os.sep)
            debug("Setting etc path to %s for os release detection"
                  % ETC_PATH)
        elif kv.key == 'PersistencePath':
            global PERSISTENCE_PATH
            PERSISTENCE_PATH = kv.values[0]
            load_persistent_data()
        elif kv.key == 'HostMetadata':
            global HOST_METADATA
            HOST_METADATA = kv.values[0]

    if not POST_URLS:
        POST_URLS = [DEFAULT_POST_URL]

    if API_TOKENS and len(POST_URLS) != len(API_TOKENS):
        log(
            "You have specified a different number of Tokens than URLs, "
            "please fix this")
        sys.exit(0)

    if NOTIFICATIONS:
        log("sending collectd notifications")
        collectd.register_notification(receive_notifications)
    else:
        collectd.register_notification(steal_host_from_notifications)

    collectd.register_write(write)

    if UTILIZATION:
        collectd.register_read(UTILIZATION_INSTANCE.read, 1,
                               name="utilization_reads")

    if OVERALLCPUUTIL is not True:
        log("Overall cpu utilization has been disabled via configuration")

    if PERCORECPUUTIL is True:
        log("Cpu utilization per core has been enabled via configuration")

    if HOST_METADATA:
        restore_sigchld()

    collectd.register_read(send, INTERVAL)
    DOGSTATSD_INSTANCE.init_callback()
    get_aws_info()


def load_persistent_data():
    """Load persistent data from a specified path"""
    try:
        with open(os.path.join(PERSISTENCE_PATH, PERSISTENCE_FILE), 'r') as js:
            persist = json.load(js)
            debug("Loaded the following persistent data %s" % persist)
            if SAVED_HOST_KEY in persist:
                global SAVED_HOST
                SAVED_HOST = persist[SAVED_HOST_KEY]
            if NEXT_METADATA_SEND_KEY in persist:
                global NEXT_METADATA_SEND
                NEXT_METADATA_SEND = persist[NEXT_METADATA_SEND_KEY]
            if NEXT_METADATA_SEND_INTERVAL_KEY in persist:
                global NEXT_METADATA_SEND_INTERVAL
                NEXT_METADATA_SEND_INTERVAL = \
                    persist[NEXT_METADATA_SEND_INTERVAL_KEY]

    except Exception as e:
        debug("Unable to load persistence data %s" % e)


def save_persistent_data():
    """Persist data about the metadata plugin to a file"""
    if PERSISTENCE_PATH:
        try:
            with open(os.path.join(PERSISTENCE_PATH,
                                   PERSISTENCE_FILE), 'w') as f:
                persist = {
                    SAVED_HOST_KEY: HOST,
                    NEXT_METADATA_SEND_KEY: NEXT_METADATA_SEND,
                    NEXT_METADATA_SEND_INTERVAL_KEY:
                        NEXT_METADATA_SEND_INTERVAL
                }
                json.dump(persist, f)
        except Exception as e:
            debug("Unable to save persistent data: %s" % e)


def compact(thing):
    return json.dumps(thing, separators=(',', ':'))


def write(values_obj):
    if UTILIZATION:
        UTILIZATION_INSTANCE.write(values_obj)

    # race notifications for grabbing host
    steal_host_from_notifications(values_obj)

    global MAX_LENGTH
    if not MAX_LENGTH and values_obj.plugin == PLUGIN_NAME and PLUGIN_UPTIME \
            in values_obj.type_instance \
            and values_obj.type_instance[-1] is not "]":
        MAX_LENGTH = len(values_obj.type_instance)
        log("This collectd has a limit of %s characters; will adhere to "
            "that" % MAX_LENGTH)


def send():
    """
    Sends datapoints and metadata events

    dimensions existing
    """

    send_datapoints()
    DOGSTATSD_INSTANCE.read_callback()

    send_top()

    if not HOST_METADATA:
        return
    # race condition with host dimension existing
    # don't send metadata on initial iteration, but on a random interval in
    # the first six, send it then one minute later, then one hour, then one
    # day, then once a day from then on but off by a fudge factor
    global NEXT_METADATA_SEND
    if NEXT_METADATA_SEND == 0:
        dither = NEXT_METADATA_SEND_INTERVAL.pop(0)
        NEXT_METADATA_SEND = time.time() + dither
        log("adding small dither of %s seconds before sending notifications"
            % dither)
        save_persistent_data()
    if NEXT_METADATA_SEND < time.time():
        send_notifications()
        if len(NEXT_METADATA_SEND_INTERVAL) > 1:
            NEXT_METADATA_SEND = \
                time.time() + NEXT_METADATA_SEND_INTERVAL.pop(0)
        else:
            NEXT_METADATA_SEND = time.time() + NEXT_METADATA_SEND_INTERVAL[0]

        log("till next metadata %s seconds"
            % str(NEXT_METADATA_SEND - time.time()))
        save_persistent_data()

    global LAST
    LAST = time.time()


def reset_metadata_send():
    """Reset the next metadata send and the metadata send intervals"""
    debug("Resetting the next metadata send time and metadata send intervals.")
    global NEXT_METADATA_SEND
    NEXT_METADATA_SEND = DEFAULT_NEXT_METADATA_SEND()
    global NEXT_METADATA_SEND_INTERVAL
    NEXT_METADATA_SEND_INTERVAL = DEFAULT_NEXT_METADATA_SEND_INTERVAL()


def all_interfaces():

    """
        On macosx only use netifaces
        :return: all ip addresses by interface.
                 or empty list if netifaces not installed
    """
    if sys.platform == 'darwin':
        ifaces = []
        try:
            for interface in interfaces():
                for link in ifaddresses(interface).get(AF_INET, ()):
                    ifaces.append((interface, link['addr']))
        except:
            pass
        return ifaces
    else:
        """
        source # http://bit.ly/1K8LIFH
        could use netifaces but want to package as little code as possible

        :return: all ip addresses by interface
        """
        is_64bits = struct.calcsize("P") == 8
        struct_size = 32
        if is_64bits:
            struct_size = 40
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        max_possible = 8  # initial value
        while True:
            _bytes = max_possible * struct_size
            names = array.array('B')
            for i in range(0, _bytes):
                names.append(0)
            outbytes = struct.unpack('iL', fcntl.ioctl(
                s.fileno(),
                0x8912,  # SIOCGIFCONF
                struct.pack('iL', _bytes, names.buffer_info()[0])
            ))[0]
            if outbytes == _bytes:
                max_possible *= 2
            else:
                break
        namestr = names.tostring()
        ifaces = []
        for i in range(0, outbytes, struct_size):
            iface_name = bytes.decode(namestr[i:i + 16]).split('\0', 1)[0]
            iface_addr = socket.inet_ntoa(namestr[i + 20:i + 24])
            ifaces.append((iface_name, iface_addr))

        return ifaces


def get_interfaces(host_info={}):
    """populate host_info with the ipaddress and fqdn for each interface"""
    interfaces = {}
    for interface, ipaddress in all_interfaces():
        if ipaddress == "127.0.0.1":
            continue
        interfaces[interface] = \
            (ipaddress, socket.getfqdn(ipaddress))
    host_info["sf_host_interfaces"] = compact(interfaces)


def get_cpu_info(host_info={}):

    """populate host_info with cpu information"""
    if sys.platform == 'darwin':
        host_info["host_cpu_model"] = \
            popen(["sysctl", "-n", "machdep.cpu.brand_string"])
        host_info["host_cpu_cores"] = \
            popen(["sysctl", "-n", "machdep.cpu.core_count"])
        host_info["host_logical_cpus"] = \
            popen(["sysctl", "-n", "hw.logicalcpu"])

        num_processor_result = popen(["system_profiler", "SPHardwareDataType"])
        for x in num_processor_result.splitlines():
            if x.strip().startswith("Number of Processors"):
                host_info["host_physical_cpus"] = \
                    x.strip().split(":")[1].strip()
                break

    else:
        with open(os.path.join(psutil.PROCFS_PATH, "cpuinfo")) as f:
            nb_cpu = 0
            nb_cores = 0
            nb_units = 0
            for p in f.readlines():
                if ':' in p:
                    x, y = map(lambda x: x.strip(), p.split(':', 1))
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
            host_info["host_cpu_model"] = model
            host_info["host_physical_cpus"] = str(nb_cpu)
            host_info["host_cpu_cores"] = str(nb_cores)
            host_info["host_logical_cpus"] = str(nb_units)

    return host_info


def get_kernel_info(host_info={}):
    """
    gets kernal information from platform, relies on the restore_sigchld
    call above to work on python 2.6
    """
    try:
        host_info["host_kernel_name"] = platform.system()
        host_info["host_machine"] = platform.machine()
        host_info["host_processor"] = platform.processor()
    except:
        log("still seeing exception in platform module")

    return host_info


def get_aws_info(host_info={}):
    """
    call into aws to get some information about the instance, timeout really
    small for non aws systems.
    """
    global AWS
    url = "http://169.254.169.254/latest/dynamic/instance-identity/document"
    try:
        req = urllib2.Request(url)
        response = urllib2.urlopen(req, timeout=0.2)
        identity = json.loads(response.read())
        want = {
            'availability_zone': 'availabilityZone',
            'instance_type': 'instanceType',
            'instance_id': 'instanceId',
            'image_id': 'imageId',
            'account_id': 'accountId',
            'region': 'region',
            'architecture': 'architecture',
        }
        for k, v in iter(want.items()):
            host_info["aws_" + k] = identity[v]
        AWS = True
        set_aws_url(host_info)
        log("is an aws box")
    except:
        log("not an aws box")
        AWS = False

    return host_info


def set_aws_url(host_info):
    global AWS_SET, POST_URLS
    if AWS and not AWS_SET:
        for i in range(len(POST_URLS)):
            result = urlparse(POST_URLS[i])
            if "sfxdim_AWSUniqueId" not in result.query:
                dim = "sfxdim_AWSUniqueId=%s_%s_%s" % \
                      (host_info["aws_instance_id"],
                       host_info["aws_region"], host_info["aws_account_id"])
                if result.query:
                    POST_URLS[i] += "&%s" % dim
                else:
                    POST_URLS[i] += "?%s" % dim
                log("adding %s to post_url for uniqueness" % dim)
            AWS_SET = True


def popen(command, include_stderr=False):
    """ using subprocess instead of check_output for 2.6 comparability """
    out, err = subprocess.Popen(command,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE).communicate()
    return out.strip() + err.strip() if include_stderr else out.strip()


def get_collectd_version():
    """
    exec the pid (which will be collectd) with help and parse the help
    message for the version information
    """

    global COLLECTD_VERSION
    if COLLECTD_VERSION:
        return COLLECTD_VERSION

    COLLECTD_VERSION = "UNKNOWN"
    try:
        if "COLLECTD_VERSION" in os.environ:
            COLLECTD_VERSION = os.environ.get("COLLECTD_VERSION")
        else:
            if sys.platform == 'darwin':
                output = popen(["/usr/local/sbin/collectd", "-h"])
            else:
                output = popen(["/proc/self/exe", "-h"], include_stderr=True)

            regexed = re.search("collectd (.*), http://collectd.org/",
                                output.decode())
            if regexed:
                COLLECTD_VERSION = regexed.groups()[0]
    except Exception:
        t, e = sys.exc_info()[:2]
        log("trying to parse collectd version failed %s" % e)

    return COLLECTD_VERSION


def get_signalfx_agent_version():
    global SIGNALFX_AGENT_VERSION
    if SIGNALFX_AGENT_VERSION:
        return SIGNALFX_AGENT_VERSION

    SIGNALFX_AGENT_VERSION = "NOT_INSTALLED"
    if "SIGNALFX_AGENT_VERSION" in os.environ:
        SIGNALFX_AGENT_VERSION = os.environ.get("SIGNALFX_AGENT_VERSION")

    return SIGNALFX_AGENT_VERSION


def getLsbRelease():
    path = os.path.join(ETC_PATH, "lsb-release")
    if os.path.isfile(path):
        with open(path) as f:
            for line in f.readlines():
                regexed = re.search('DISTRIB_DESCRIPTION="(.*)"', line)
                if regexed:
                    return regexed.groups()[0]


def getOsRelease():
    path = os.path.join(ETC_PATH, "os-release")
    if os.path.isfile(path):
        with open(path) as f:
            for line in f.readlines():
                regexed = re.search('PRETTY_NAME="(.*)"', line)
                if regexed:
                    return regexed.groups()[0]


def getCentos():
    for file in [os.path.join(ETC_PATH, "centos-release"),
                 os.path.join(ETC_PATH, "redhat-release"),
                 os.path.join(ETC_PATH, "system-release")]:
        if os.path.isfile(file):
            with open(file) as f:
                line = f.read()
                return line.strip()


def get_linux_version():
    """
    read a variety of files to figure out linux version
    """

    global LINUX_VERSION
    if LINUX_VERSION:
        return LINUX_VERSION

    for f in [getLsbRelease, getOsRelease, getCentos]:
        version = f()
        if version:
            LINUX_VERSION = version
            return LINUX_VERSION

    LINUX_VERSION = "UNKNOWN"
    return LINUX_VERSION


def parse_bytes(possible_bytes):
    """bytes can be compressed with suffixes but we want real numbers in kb"""
    try:
        return int(possible_bytes)
    except:
        if possible_bytes[-1].lower() == 'm':
            return int(float(possible_bytes[:-1]) * 1024)
        if possible_bytes[-1].lower() == 'g':
            return int(float(possible_bytes[:-1]) * 1024 ** 2)
        if possible_bytes[-1].lower() == 't':
            return int(float(possible_bytes[:-1]) * 1024 ** 3)
        if possible_bytes[-1].lower() == 'p':
            return int(float(possible_bytes[:-1]) * 1024 ** 4)
        if possible_bytes[-1].lower() == 'e':
            return int(float(possible_bytes[:-1]) * 1024 ** 5)


def parse_priority(priority):
    """
    priority can sometimes be "rt" for real time, make that 99, the highest
    """
    try:
        return int(priority)
    except:
        return 99


def to_time(secs):
    minutes = int(secs / 60)
    seconds = secs % 60.0
    sec = int(seconds)
    dec = int((seconds - sec) * 100)
    return "%02d:%02d.%02d" % (minutes, sec, dec)


def read_proc_file(pid, file, field=None):
    with open(os.path.join(psutil.PROCFS_PATH, str(pid), file)) as f:
        if not field:
            return f.read().strip()
        for x in f.readlines():
            if x.startswith(field):
                return x.split(":")[1].strip()


def get_priority(pid):

    if sys.platform == 'darwin':
        result = popen(["ps", "-O", "pri", "-p", str(pid)]).splitlines()
        return result[1].split()[1]
    else:
        val = read_proc_file(pid, "sched", "prio")
        val = int(val) - 100
        if val < 0:
            val = 99
        return val


def get_command(p):
    val = " ".join(p.cmdline())
    if not val:
        val = read_proc_file(p.pid, "status", "Name")
        val = "[%s]" % val
    return val


def get_nice(p):
    val = read_proc_file(p.pid, "stat")
    return val.split()[18]


def send_top():
    """
    Parse top unless told not to
    filter out any zeros and common values to save space send it directly
    without going through collectd mechanisms because it is too large
    """
    if not PROCESS_INFO:
        return

    status_map = {
        "sleeping": "S",
        "uninterruptible sleep": "D",
        "running": "R",
        "traced": "T",
        "stopped": "T",
        "zombie": "Z",
    }

    # send version up with the values
    response = {"v": VERSION}
    top = {}
    for p in psutil.process_iter():
        try:
            command_value = p.name()
            if sys.platform != 'darwin':
                cpu_nice_value = get_nice(p)
                command_value = get_command(p)
            else:
                cpu_nice_value = p.nice()

            if psutil.version_info >= (4, 0, 0):
                mem_info = p.memory_info()
            else:
                mem_info = p.memory_info_ex()

            top[p.pid] = [
                p.username(),  # user
                get_priority(p.pid),  # priority
                cpu_nice_value,  # nice value, numerical
                mem_info[1] / 1024,  # virtual memory size in kb
                mem_info[0] / 1024,  # resident memory size in kb
                mem_info[2] / 1024,  # shared memory size in kb
                status_map.get(p.status(), "D"),  # process status
                p.cpu_percent(),  # % cpu, float
                p.memory_percent(),  # % mem, float
                to_time(p.cpu_times().system + p.cpu_times().user),  # cpu
                command_value  # command
            ]
        except Exception:
            # eat exceptions here because they're very noisy
            pass

    s = compact(top)
    compressed = zlib.compress(s.encode("utf-8"))
    base64 = binascii.b2a_base64(compressed)
    response["t"] = base64.decode("utf-8")
    response_json = compact(response)
    notif = LargeNotif(response_json, TOP_TYPE_INSTANCE, VERSION)
    receive_notifications(notif)


def get_memory(host_info):

    if sys.platform == 'darwin':
        host_info["host_mem_total"] = \
            str(int(popen(["sysctl", "-n", "hw.memsize"])) / 1024)
    else:
        """get total physical memory for machine"""
        with open(os.path.join(psutil.PROCFS_PATH, "meminfo")) as f:
            pieces = f.readline()
            _, mem_total, _ = pieces.split()
            host_info["host_mem_total"] = mem_total

    return host_info


def get_host_info():
    """ aggregate all host info """
    host_info = {}
    get_cpu_info(host_info)
    get_kernel_info(host_info)
    get_aws_info(host_info)
    get_memory(host_info)
    get_interfaces(host_info)
    host_info["host_metadata_version"] = VERSION
    host_info["host_collectd_version"] = get_collectd_version()
    host_info["host_signalfx_agent_version"] = get_signalfx_agent_version()
    host_info["host_linux_version"] = get_linux_version()
    host_info["host_kernel_release"] = platform.release()
    host_info["host_kernel_version"] = platform.version()
    return host_info


def map_diff(host_info, old_host_info):
    """
    diff old and new host_info for additions of modifications
    don't look for removals as they will likely be spurious
    """
    diff = {}
    for k, v in iter(host_info.items()):
        if k not in old_host_info:
            diff[k] = v
        elif old_host_info[k] != v:
            diff[k] = v
    return diff


def put_val(plugin_instance, type_instance, val, plugin=PLUGIN_NAME, t=0.0,
            i=INTERVAL):
    """Create collectd metric"""
    try:
        if __name__ != "__main__":
            collectd.Values(plugin=plugin,
                            time=t,
                            plugin_instance=plugin_instance,
                            type=val[1].lower(),
                            meta={'0': True},
                            type_instance=type_instance,
                            interval=i,
                            values=[val[0]]).dispatch()
        else:
            h = platform.node()
            print('PUTVAL %s/%s/%s-%s interval=%d N:%s' % (
                h, PLUGIN_NAME, val[1].lower(),
                type_instance, INTERVAL, val[0]))
    except TypeError:
        global UTILIZATION
        if UTILIZATION:
            UTILIZATION = False
            log("ERROR: Utilization features have been disabled because " +
                "TypesDB hasn't been specified")
            log(
                "To use the utilization features of this plugin, please " +
                "update the top of your config to include 'TypesDB " +
                "\"/opt/signalfx-collectd-plugin/types.db.plugin\"'")


def get_uptime():
    """get uptime for plugin"""
    return time.time() - UP


def send_datapoints():
    """
    emit three datapoints:
     - sf.host-resposne.errors : number of errors seen this interval sending
     notifications (if any)
     - sf.host-response.max : max round trip time in nanoseconds it took to
     send notifications (if any)
     - sf.host-plugin_uptime : uptime in seconds of the plugin with
     dimensions containing metadata
    :return: None
    """

    if not DATAPOINTS:
        return

    plugin_instance = "[metadata=%s,collectd=%s,signalfx_agent=%s]" % (
        VERSION, get_collectd_version(), get_signalfx_agent_version())
    type_instance = "%s[linux=%s,release=%s,version=%s]" % (
        PLUGIN_UPTIME, get_linux_version(), platform.release(),
        platform.version())
    if MAX_LENGTH and len(type_instance) > MAX_LENGTH:
        type_instance = PLUGIN_UPTIME
    put_val(plugin_instance, type_instance, [get_uptime(), "gauge"])
    global MAX_RESPONSE
    maximum = MAX_RESPONSE
    MAX_RESPONSE = 0
    if maximum:
        put_val("", "sf.host-response.max", [maximum, "gauge"])

    put_val("", "sf.host-response.errors", [RESPONSE_ERRORS, "counter"])


def putnotif(property_name, message, plugin_name=PLUGIN_NAME,
             type_instance=HOST_TYPE_INSTANCE, type=TYPE):
    """Create collectd notification"""
    if __name__ != "__main__":
        notif = collectd.Notification(plugin=plugin_name,
                                      plugin_instance=property_name,
                                      type_instance=type_instance,
                                      type=type)
        notif.severity = 4  # OKAY
        notif.message = message
        notif.dispatch()
    else:
        h = platform.node()
        print('PUTNOTIF %s/%s-%s/%s-%s %s' % (h, plugin_name, property_name,
                                              type, type_instance, message))


def write_notifications(host_info):
    """emit any new notifications"""
    for property_name, property_value in iter(host_info.items()):
        if len(property_value) > 255:
            receive_notifications(LargeNotif(property_value,
                                             HOST_TYPE_INSTANCE,
                                             property_name))
        else:
            putnotif(property_name, property_value)


def send_notifications():
    if HOST_METADATA:
        host_info = get_host_info()
        write_notifications(host_info)


def get_severity(severity_int):
    """
    helper meethod to swap severities

    :param severity_int: integer value for severity
    :return: collectd string for severity
    """
    return {
        1: "FAILURE",
        2: "WARNING",
        4: "OKAY"
    }[severity_int]


def update_response_times(diff):
    """
    Update max response time

    :param diff: how long a round trip took
    :return: None
    """
    with RESPONSE_LOCK:
        global MAX_RESPONSE
        if diff > MAX_RESPONSE:
            MAX_RESPONSE = diff


def steal_host_from_notifications(notif):
    """
    callback to consume notifications from collectd and steal host name from it
    even if we don't want to have the plugin send them.
    :param notif: notification
    :return: true if should continue, false if not
    """

    if not notif:
        return False

    if __name__ == "__main__":
        log(notif)
        return False

    # we send our own notifications but we don't have access to collectd's
    # "host" from collectd.conf steal it from notifications we've put on the
    # bus so we can use it for our own
    global HOST
    global SAVED_HOST
    if not HOST and notif.host:
        HOST = notif.host
        # if host is identified and it's different from the saved_host,
        # reset the metadata send interval and next metadata send time
        if SAVED_HOST and SAVED_HOST != HOST:
            debug(("The saved hostname '{0}' does not match the current "
                   "hostname '{1}'.").format(SAVED_HOST, HOST))
            reset_metadata_send()
            SAVED_HOST = HOST
        DOGSTATSD_INSTANCE.set_host(notif.host)
        log("found host " + HOST)

    return True


def receive_notifications(notif):
    """
    callback to consume notifications from collectd and emit them to SignalFx.
    callback will only be called if Notifications was configured to be true.
    Only send notifications created by other plugs which are above or equal
    the configured NotifyLevel.
    """

    if not steal_host_from_notifications(notif):
        return

    notif_dict = {}
    # because collectd c->python is a bit limited and lacks __dict__
    for x in ['host', 'message', 'plugin', 'plugin_instance', 'severity',
              'time', 'type', 'type_instance']:
        notif_dict[x] = getattr(notif, x, "")

    # emit notifications that are ours, or satisfy the notify level
    if notif_dict['plugin'] != PLUGIN_NAME and notif_dict['type'] != TYPE \
            and notif_dict['type_instance'] not in [HOST_TYPE_INSTANCE,
                                                    TOP_TYPE_INSTANCE] \
            and notif_dict["severity"] > NOTIFY_LEVEL:
        log("event ignored: " + str(notif_dict))
        return

    if not notif_dict["time"]:
        notif_dict["time"] = time.time()
    if not notif_dict["host"]:
        if HOST:
            notif_dict["host"] = HOST
        log("no host info, setting to " + notif_dict["host"])

    notif_dict["severity"] = get_severity(notif_dict["severity"])
    data = compact([notif_dict])
    headers = {"Content-Type": "application/json"}
    for i in range(len(POST_URLS)):
        post_url = POST_URLS[i]
        if API_TOKENS:
            headers["X-SF-TOKEN"] = API_TOKENS[i]
        start = time.time()
        try:
            req = urllib2.Request(post_url, data, headers)
            urllib2.urlopen(req, timeout=TIMEOUT)
        except Exception:
            t, e = sys.exc_info()[:2]
            sys.stdout.write(str(e))
            log("unsuccessful response: %s" % str(e))
            global RESPONSE_ERRORS
            RESPONSE_ERRORS += 1
        finally:
            diff = time.time() - start
            update_response_times(diff * 1000000.0)


def restore_sigchld():
    """
    Restores the SIGCHLD handler if needed

    See https://github.com/deniszh/collectd-iostat-python/issues/2 for
    details.
    """
    try:
        platform.system()
    except:
        log("executing SIGCHLD workaround")
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)


# Note: Importing collectd_dogstatsd registers its own endpoints

if __name__ != "__main__":
    collectd.register_config(plugin_config)
    collectd.register_shutdown(DOGSTATSD_INSTANCE.register_shutdown)

else:
    # outside plugin just collect the info
    restore_sigchld()
    send()
    log(json.dumps(get_host_info(), sort_keys=True,
                   indent=4, separators=(',', ': ')))
    if len(sys.argv) < 2:
        while True:
            time.sleep(INTERVAL)
            send()
