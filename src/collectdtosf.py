import os
import sys
import math
import re
import logging
import logging.config

import collectd


sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(os.path.dirname(__file__))
from datapointuploader import DatapointUploader, DataPoint

log = logging.getLogger(__name__)

VERSION = "0.0.2"
PLUGIN_NAME = 'collectd-signalfx'
WHITELISTED_VALUES = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-:")


def whitelist_field(field):
    """
    Make a source or metric name suitable for ingest.
    """

    field = field.strip().replace(" ", "_")
    ret = ""
    for c in field:
        if c in WHITELISTED_VALUES:
            ret += c
    return ret


def parse_types_file(path):
    """
    Parse a collectd types from as defined from
    http://collectd.org/documentation/manpages/types.db.5.shtml
    """
    types = {}

    # Types at https://collectd.org/wiki/index.php/Data_source
    conversions = {
        # Our system cannot differentiate between counter and derive, cumulative_counter is mostly
        # correct.
        "COUNTER": "CUMULATIVE_COUNTER",
        "DERIVE": "CUMULATIVE_COUNTER",
        "GAUGE": "GAUGE",
        "ABSOLUTE": "COUNTER",
    }

    with open(path, 'r') as f:
        # Example line:
        # if_octets  rx:COUNTER:0:4294967295, tx:COUNTER:0:4294967295
        for line in f:
            line = line.strip()
            # Comment line: ignore
            if line == "" or line[0] == '#':
                continue
            fields = line.split()
            if len(fields) < 2:
                # Invalid line
                continue

            name = fields[0]

            v = []
            for datasource in fields[1:]:
                datasource = datasource.rstrip(',')
                ds_fields = datasource.split(':')

                if len(ds_fields) != 4:
                    collectd.warning(
                        'plugin=%s, file=%s: Unparsable line %s' % (PLUGIN_NAME, path, line))
                    continue

                if ds_fields[1] not in conversions:
                    collectd.warning(
                        'plugin=%s, file=%s: Unknown type in line %s' % (PLUGIN_NAME, path, line))
                    continue
                v.append((ds_fields[0], conversions[ds_fields[1]]))

            types[name] = v

    return types


_underscorer1 = re.compile(r'(.)([A-Z][a-z]+)')
_underscorer2 = re.compile('([a-z0-9])([A-Z])')


def camel_case_to_snake_case(s):
    """
    Converts a string to snake case from camel case.  Code from
    https://gist.github.com/jaytaylor/3660565
    """
    subbed = _underscorer1.sub(r'\1_\2', s)
    return _underscorer2.sub(r'\1_\2', subbed).lower()


def str2bool(v):
    if type(v) == bool:
        return v
    return v.lower() in ("yes", "true", "t", "1", "y")


def get_precompiled_regular_expressions(s):
    if s == '' or s is None:
        return []
    try:
        return [re.compile(r) for r in s.split(',')]
    except Exception as e:
        log.error("Exception compiling regular expressions: %s", e)
        return []


def plugin_signalfx_write(v, data=None):
    data.write(v)


def signalfx_plugin_config(config, data):
    data.configure(config)


def signalfx_plugin_shutdown(data):
    data.shutdown()


def signalfx_plugin_read(data):
    data.read()


def signalfx_plugin_init(data):
    data.init()


class SignalFxPlugin(object):
    def __init__(self):
        self.config_setup = {
            'types_db': ('/usr/share/collectd/types.db', str),
            'metric_prefix': ('collectd', str),
            'metric_separator': ('.', str),
            'url': ('https://api.signalfuse.com', str),
            'api_token': ('', str),
            'source': ('', str),
            'debug': (False, str2bool),
            'lower_case': (False, str2bool),
            'include_regex': ('', get_precompiled_regular_expressions),
            'log_config': ('', str),
            'flush_max_measurements': (600, int),
            'max_queue_size': (20000, int),
            'timeout': (60, int),
            'queue_flush_size': (5000, int),
            'self_monitor': (True, str2bool),
            'flushing_threads': (2, int),
            'ignore_localtime': (True, str2bool),
        }
        self.config = {}
        self.data_queue = None
        self.registered_series = set()
        self.queue_full_exception = None
        self.queue_empty_exception = None
        self.registration_lock = None
        self.is_shutdown = False

        self.metrics_lock = None
        self.write_calls = 0
        self.metrics_written = 0
        self.metrics_registered = 0
        self.signalboost_calls = 0
        self.signalboost_errors = 0


    def configure(self, plugin_config):
        for k, (default, func) in self.config_setup.items():
            self.config[k] = func(default)

        for child in plugin_config.children:
            map_key = camel_case_to_snake_case(child.key)
            if map_key in self.config_setup:
                # We only consider the first option listed
                self.config[map_key] = self.config_setup[map_key][1](child.values[0])


    def parseTypesFile(self):
        self.file_types = parse_types_file(self.config['types_db'])

    def write(self, values):
        with self.metrics_lock:
            self.write_calls += 1
        if values.type not in self.file_types:
            collectd.warning('%s: do not know how to handle type %s. '
                             'do you have all your types.db files configured?  This message is ok'
                             ' if expected' % \
                             (PLUGIN_NAME, values.type))
            # Default to gauge
            self.file_types[values.type] = [('', "GAUGE")] * len(values.values)

        v_type = self.file_types[values.type]

        if len(v_type) != len(values.values):
            collectd.warning('%s: differing number of values for type %s %s vs %s' % \
                             (PLUGIN_NAME, values.type, v_type, values.values))
            return

        name_parts = [elem for elem in [self.config['metric_prefix'],
                                        values.plugin,
                                        values.plugin_instance,
                                        values.type,
                                        values.type_instance
        ] if elem != None and elem != False and len(elem) > 0]

        source = next((s for s in [self.config['source'], values.host, 'CollectD'] if
                       s is not None and len(s) > 0))

        for (value, (data_name, data_type)) in zip(values.values, v_type):
            # Can value be None?
            if value is None or math.isnan(value):
                continue

            metric_parts = list(name_parts)
            if len(values.values) > 1:
                metric_parts.append(data_name)

            metric_name = self.config['metric_separator'].join(metric_parts)
            if self.config['lower_case']:
                metric_name = metric_name.lower()

            matches = len(self.config['include_regex']) == 0
            for regex in self.config['include_regex']:
                if regex.match(metric_name):
                    matches = True
                    break

            if not matches:
                continue

            time_to_write = int(values.time)
            if self.config['ignore_localtime']:
                time_to_write = 0
            datapoint = DataPoint(whitelist_field(source), whitelist_field(metric_name),
                                  float(value), data_type, time_to_write)
            try:
                self.data_queue.put_nowait(datapoint)
            except self.queue_full_exception as e:
                pass

    def shutdown(self):
        log.info("Shutdown called")
        for x in xrange(self.config['flushing_threads']):
            self.data_queue.put_nowait(None)
        self.is_shutdown = True

    def drainMyQueue(self):
        try:
            self.drainMyQueueImpl()
        except Exception as e:
            if not self.is_shutdown:
                log.exception("Draining queue shut down!: %s", e)

    def drainMyQueueImpl(self):
        log.info("Starting a drain queue: %s", self.config['api_token'])
        url = self.config['url']
        try:
            signalboost_wrapper = DatapointUploader(
                self.config['api_token'], url, timeout=self.config['timeout'],
                user_agent_name=PLUGIN_NAME, user_agent_version=VERSION)
        except Exception as e:
            collectd.warning(
                'Not reporting data to SignalFx. Check the SignalFx plugin '
                'log.')
            log.info(
                'Unable to create the DatapointUploader object. Check the URL, '
                'the token, and your connectivity to the service at ({0}).'.
                format(url))
            raise
        log.info("Wrapper made")
        while self.is_shutdown == False:
            # Block for an item
            dp = self.data_queue.get()
            if dp is None:
                continue
            items = [dp]
            # Now loop not blocking and get some items
            while len(items) < self.config['queue_flush_size']:
                try:
                    dp = self.data_queue.get_nowait()
                    if dp is None:
                        return  # We need to die.  Don't bother flushing metrics
                    items.append(dp)
                except self.queue_empty_exception as e:
                    break

            unregistered_metrics = set()
            with self.registration_lock:
                metrics_in_register_set = set()
                # TODO(jack): Consider removing metrics_to_register
                metrics_to_register = []
                for item in items:
                    if item.metric not in self.registered_series and item.metric not in \
                            metrics_in_register_set:
                        metrics_in_register_set.add(item.metric)
                        metrics_to_register.append(item)
                if len(metrics_to_register):
                    log.info("Registering %d metrics", len(metrics_to_register))
                    with self.metrics_lock:
                        self.signalboost_calls += 1
                    r = signalboost_wrapper.registerMultipleSeries(metrics_to_register)
                    assert (len(r) == len(metrics_to_register))
                    for (item, was_able_to_register) in zip(metrics_to_register, r):
                        if was_able_to_register:
                            with self.metrics_lock:
                                self.metrics_registered += 1
                            self.registered_series.add(item.metric)
                        else:
                            unregistered_metrics.add(item.metric)

            items = [i for i in items if i.metric not in unregistered_metrics]
            if len(items) == 0:
                log.info("No items left to add datapoints for")
                continue
            with self.metrics_lock:
                self.metrics_written += len(items)
            log.info("Draining %d items", len(items))
            with self.metrics_lock:
                self.signalboost_calls += 1
            res = signalboost_wrapper.addDatapoints(items)
            log.debug("Add datapoints result: %s", res)
            if self.config['debug']:
                with open("/tmp/flush_times", "w") as myfile:
                    for item in items:
                        myfile.write(str(item) + "\n")
        log.info("Drain done???")
        signalboost_wrapper.disconnect()

    def read(self):
        with self.metrics_lock:
            towrite = {
                'write_calls': self.write_calls,
                'metrics_written': self.metrics_written,
                'metrics_registered': self.metrics_registered,
                'signalboost_calls': self.signalboost_calls,
                'signalboost_errors': self.signalboost_errors,
                'queue_size': self.data_queue.qsize(),
            }

        for k, v in towrite.items():
            vl = collectd.Values(type='derive')
            vl.plugin = self.config['metric_separator'].join([PLUGIN_NAME, k])
            vl.dispatch(values=[v])


    def init(self):
        # I can't import Queue until init() is called, because documentation says don't use the
        # threading library (which queue uses) until init() is called first.
        import Queue
        import threading

        self.queue_full_exception = Queue.Full
        self.queue_empty_exception = Queue.Empty

        if self.config['log_config'] != '':
            logging.config.fileConfig(self.config['log_config'], disable_existing_loggers=False)

        try:
            self.parseTypesFile()
        except:
            msg = "Unable to parse types.db file %s", self.config['types_db']
            collectd.error(msg)
            raise Exception(msg)

        for k, v in self.config.items():
            log.debug("Using config %s=%s", k, v)
        self.data_queue = Queue.Queue(maxsize=self.config['max_queue_size'])
        self.registration_lock = threading.Lock()
        self.metrics_lock = threading.Lock()
        collectd.register_write(plugin_signalfx_write, data=self)
        threads = []
        for x in xrange(self.config['flushing_threads']):
            log.debug("Creating flushing threads")
            threads.append(threading.Thread(target=SignalFxPlugin.drainMyQueue, args=(self,)))
        log.debug("Starting threads")
        [t.start() for t in threads]
        if self.config['self_monitor']:
            log.debug("Registering read callback!")
            collectd.register_read(signalfx_plugin_read, data=plugin_data)


plugin_data = SignalFxPlugin()
collectd.register_shutdown(signalfx_plugin_shutdown, data=plugin_data)
collectd.register_config(signalfx_plugin_config, data=plugin_data)
collectd.register_init(signalfx_plugin_init, data=plugin_data)
