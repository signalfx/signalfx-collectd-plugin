#!/usr/bin/python

# script to send process-specific metrics to collectd
# also sends container-specific metrics
# writes in collectd text protocol format
#
# Usage:
# You can run this stand-alone (it outputs text in
# exec plugin format), or you can run it as a
# collectd plugin
# For standalone usage, see config in code below
# How to run standalone:
# python collectd-ps-plugin.py
import sys

if __name__ != '__main__':
    import collectd

import os
import time

import psutil
from docker import Client


def log(param):
    """ log messages and understand if we're in collectd or a program """
    if __name__ != '__main__':
        collectd.info("%s: %s" % (PLUGIN_NAME, param))
    else:
        sys.stderr.write("%s\n" % param)

# CONFIG
MIN_RUN_INTERVAL = 0
MIN_CPU_USAGE_PERCENT = 0
MIN_MEM_USAGE_PERCENT = 0
DEBUG_DO_FILTER_PROCESSES = True
REPORT_DOCKER_CONTAINER_NAMES = False

# GLOBALS
dclnt = None
DOCKER_SOCKET_URL = 'unix:///var/run/docker.sock'
PLUGIN_NAME = 'processwatch'
INTERVAL = 10  # only if running stand-alone


# process-metrics
pm = {
    # format:
    # internal_define: ['external_name','type','min','max']
    'PM_CPU_PCT': ['process.cpu.percent', 'GAUGE', '0', '100'],
    'PM_MEM_PCT': ['process.mem.percent', 'GAUGE', '0', '100'],
    'PM_RUN_SECS': ['process.runtime.seconds', 'COUNTER', 'U', 'U'],
    'PM_BYTES_READ': ['process.bytes.read', 'COUNTER', 'U', 'U'],
    'PM_BYTES_WRITE': ['process.bytes.write', 'COUNTER', 'U', 'U'],
    'PM_OPEN_FDS': ['process.fds.open', 'COUNTER', 'U', 'U'],
    'PM_NUM_THREADS': ['process.threads.count', 'COUNTER', 'U', 'U'],
    'PM_NUM_CTX_SWITCHES_VOL':
        ['process.cpu.contextswitches.voluntary', 'COUNTER', 'U', 'U'],
    'PM_NUM_CTX_SWITCHES_INVOL':
        ['process.cpu.contextswitches.involuntary', 'COUNTER', 'U', 'U'],
}


def set_process_metric_val(mmap, mname, mval):
    mmap[pm[mname][0]] = (mval, pm[mname][1])


def get_process_metric_val(mmap, mname):
    return mmap[pm[mname][0]][0]


def write_types_db_metrics(mm, f):
    for v in mm.values():
        out_line = '%s\tvalue:%s:%s:%s\n' % (v[0], v[1], v[2], v[3])
        f.write(out_line)


# end metrics


def get_docker_container_id(pid):
    with open('/proc/' + str(pid) + '/cgroup') as f:
        pcgline = f.readline()
    # XXX:VERIFY: we assume a docker process won't belong to
    # multiple containers
    pcglist = pcgline.split('/')
    pdockerid = None
    if len(pcglist) > 2 and pcglist[1] == 'docker':
        pdockerid = pcglist[2].rstrip()
    return pdockerid


def get_docker_container_name(pid):
    dcname = ''
    dc_id = get_docker_container_id(pid)
    if dc_id is not None:
        log('pid %s: looking up container id: %d' % (pid, dc_id))
        try:
            dcinfo = dclnt.inspect_container(dc_id)
        except:
            log('error getting container info:' +
                ' check your script user/group' +
                'is OK in collectd.conf')
            return dcname
        dcname = dcinfo['Name'][1:]  # strip beginning '/'
        log('pid %s: returning container name: %s' % (pid, dcname))
    return dcname


def mk_process_name(in_pname, pid, ppid):
    pname = in_pname
    dcname = ''
    if REPORT_DOCKER_CONTAINER_NAMES:
        dcname = get_docker_container_name(pid)
    # collectd has special meaning for '-'
    pname = pname.replace('/', '_').replace('-', '_')
    pname += '[pid=%d,ppid=%d' % (pid, ppid)
    if dcname != '':
        pname += ',containername=%s' % (dcname)
    pname += ']'
    return pname


def populate_process_metrics(proc):
    ACCESS_DENIED = ''
    try:
        pinfo = proc.as_dict(ad_value=ACCESS_DENIED)
    except psutil.NoSuchProcess:
        log('process disappeared')
        # it went away
        return None, None
    pid = pinfo['pid']
    ppid = pinfo['ppid']
    pruntime = time.time() - pinfo['create_time']
    pcpupct = pinfo['cpu_percent']
    pmempct = round(pinfo['memory_percent'], 1)
    pnopenfds = pinfo['num_fds']
    pname = os.path.basename(pinfo['exe'])
    # happens for kernel threads
    if pname == '':
        pname = pinfo['name']
    if pnopenfds == '':
        pnopenfds = 0
    pnthreads = pinfo['num_threads']
    pnctxsw_vol = pinfo['num_ctx_switches'][0]
    pnctxsw_invol = pinfo['num_ctx_switches'][1]
    if (DEBUG_DO_FILTER_PROCESSES is False
        or (pruntime >= MIN_RUN_INTERVAL
            and (pcpupct >= MIN_CPU_USAGE_PERCENT
                 or pmempct >= MIN_MEM_USAGE_PERCENT))):
        pmap = {}
        set_process_metric_val(pmap, 'PM_CPU_PCT', pcpupct)
        set_process_metric_val(pmap, 'PM_MEM_PCT', pmempct)
        set_process_metric_val(pmap, 'PM_RUN_SECS', pruntime)
        set_process_metric_val(pmap, 'PM_OPEN_FDS', pnopenfds)
        set_process_metric_val(pmap, 'PM_NUM_THREADS', pnthreads)
        set_process_metric_val(pmap, 'PM_NUM_CTX_SWITCHES_VOL', pnctxsw_vol)
        set_process_metric_val(pmap, 'PM_NUM_CTX_SWITCHES_INVOL',
                               pnctxsw_invol)
        pio = pinfo.get('io_counters', ACCESS_DENIED)
        if pio != ACCESS_DENIED:
            set_process_metric_val(pmap, 'PM_BYTES_READ',
                                   pio.read_bytes)
            set_process_metric_val(pmap, 'PM_BYTES_WRITE',
                                   pio.write_bytes)
        pname = mk_process_name(pname, pid, ppid)
        return pname, pmap
    return None, None


def get_processes_info():
    pmaps = {}
    for proc in psutil.process_iter():
        pname, pmap = populate_process_metrics(proc)
        if pname:
            pmaps[pname] = pmap
    return pmaps


def write_val(plugin_name, pname, metric, val):
    if __name__ != '__main__':
        collectd.Values(plugin=plugin_name,
                        plugin_instance=pname,
                        meta={'0': True},
                        type=val[1].lower(),
                        type_instance=metric,
                        values=[val[0]]).dispatch()
    else:
        print('PUTVAL localhost/%s-%s/%s-%s interval=%d N:%d' % (
            plugin_name, pname, val[1].lower(), metric, INTERVAL, val[0]))


def process_watch_init():
    global dclnt
    if REPORT_DOCKER_CONTAINER_NAMES:
        dclnt = Client(base_url=DOCKER_SOCKET_URL)


def str2bool(v):
    return v.lower() in ("yes", "true", "t", "1")


def process_watch_config(conf):
    global MIN_RUN_INTERVAL
    global DEBUG_DO_FILTER_PROCESSES
    global MIN_CPU_USAGE_PERCENT
    global MIN_MEM_USAGE_PERCENT
    global REPORT_DOCKER_CONTAINER_NAMES

    for kv in conf.children:
        if kv.key == 'MinRuntimeSeconds':
            # int() will throw exception if invalid
            MIN_RUN_INTERVAL = int(kv.values[0])
        elif kv.key == 'FilterProcesses':
            DEBUG_DO_FILTER_PROCESSES = kv.values[0]
            # if user typed something other than true/false
            if type(DEBUG_DO_FILTER_PROCESSES).__name__ != 'bool':
                DEBUG_DO_FILTER_PROCESSES = str2bool(kv.values[0])
        elif kv.key == 'MinCPUPercent':
            if int(kv.values[0]) == 0 or int(kv.values[0]) > 100:
                raise Exception('invalid value for ' + kv.key)
            MIN_CPU_USAGE_PERCENT = int(kv.values[0])
        elif kv.key == 'MinMemoryPercent':
            if int(kv.values[0]) == 0 or int(kv.values[0]) > 100:
                raise Exception('invalid value for ' + kv.key)
            MIN_MEM_USAGE_PERCENT = int(kv.values[0])
        elif kv.key == 'ReportDockerContainerNames':
            REPORT_DOCKER_CONTAINER_NAMES = kv.values[0]
            if type(REPORT_DOCKER_CONTAINER_NAMES).__name__ != 'bool':
                REPORT_DOCKER_CONTAINER_NAMES = str2bool(kv.values[0])
        else:
            raise Exception('unknown config parameter')
    if __name__ != "__main__":
        collectd.register_read(send_metrics)


def write_metrics(mmaps, plugin_name):
    for name, mmap in iter(mmaps.items()):
        for metric, val in iter(mmap.items()):
            write_val(plugin_name, name, metric, val)


def send_metrics():
    pmaps = get_processes_info()
    write_metrics(pmaps, PLUGIN_NAME)


if __name__ != "__main__":
    collectd.register_init(process_watch_init)
    collectd.register_config(process_watch_config)
else:
    process_watch_init()
    MIN_RUN_INTERVAL = 0
    DEBUG_DO_FILTER_PROCESSES = False
    MIN_CPU_USAGE_PERCENT = 0
    MIN_MEM_USAGE_PERCENT = 0
    REPORT_DOCKER_CONTAINER_NAMES = True
    send_metrics()
    if len(sys.argv) < 2:
        while True:
            time.sleep(INTERVAL)
            send_metrics()
