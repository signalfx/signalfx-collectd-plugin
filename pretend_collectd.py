"""
Allows unit testing python collectd modules.  Use like:

    import pretend_collectd as collectd
    import sys
    sys.modules["collectd"] = collectd

"""
import time
import copy

init_functions = []


def register_init(init_func, data):
    init_functions.append((init_func, data))


config_functions = []


def register_config(config_func, data):
    config_functions.append((config_func, data))


shutdown_functions = []


def register_shutdown(shutdown_func, data):
    shutdown_functions.append((shutdown_func, data))


error_messages = []


def error(msg):
    error_messages.append(msg)


warning_messages = []


def warning(msg):
    warning_messages.append(msg)


write_functions = []


def register_write(func, data):
    write_functions.append((func, data))


read_functions = []


def register_read(func, data):
    read_functions.append((func, data))


class Config(object):
    def __init__(self, children=[], key='', values=None):
        if not values: values = []
        self.children = children
        self.key = key
        self.values = values


class PluginData(object):
    def __init__(self, host, plugin, type, type_instance, plugin_instance='',
                 time=int(time.time() * 1000)):
        self.host = host
        self.plugin = plugin
        self.type = type
        self.type_instance = type_instance
        self.plugin_instance = plugin_instance
        self.time = time


class Values(PluginData):
    # noinspection PyShadowingBuiltins
    def __init__(self, host=None, plugin=None, type=None, type_instance=None, interval=None,
                 values=None, meta=None, plugin_instance='', time=int(time.time() * 1000)):
        if not meta: meta = {}
        super(Values, self).__init__(host, plugin, type, type_instance, plugin_instance, time)
        self.interval = interval
        self.values = values
        self.meta = meta

    def dispatch(self, **kwargs):
        to_send = copy.deepcopy(self)
        for k, v in kwargs.items():
            setattr(to_send, k, v)

        for (write_func, data) in write_functions:
            write_func(to_send, data=data)
