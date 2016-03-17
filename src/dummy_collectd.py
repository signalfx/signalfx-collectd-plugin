import logging


# pylint: disable=too-many-instance-attributes
class DummyCollectd(object):
    def __init__(self, is_running_tests=False):
        self.is_running_tests = is_running_tests
        self.registered_inits = []
        self.registered_configs = []
        self.registered_reads = []
        self.registered_logs = []
        self.registered_shutdowns = []
        self.registered_notifications = []
        self.registered_flush = []
        self.dispatched_values = []
        self.write_values = []
        self.logger = None

        # pylint: disable=invalid-name
        # Want to match the module's name for readability
        self.Values = self.values_class()

    def init_logging(self):
        self.logger = logging.getLogger(__name__)

    def register_init(self, callback):
        assert self.is_running_tests
        self.registered_inits.append(callback)

    def register_config(self, callback):
        assert self.is_running_tests
        self.registered_configs.append(callback)

    # pylint: disable=unused-argument
    def register_read(self, callback, interval=10, name=""):
        assert self.is_running_tests
        self.registered_reads.append(callback)

    # pylint: disable=unused-argument
    def register_log(self, callback, interval=10, name=""):
        assert self.is_running_tests
        self.registered_logs.append(callback)

    def register_flush(self, callback):
        assert self.is_running_tests
        self.registered_flush.append(callback)

    def register_shutdown(self, callback):
        assert self.is_running_tests
        self.registered_shutdowns.append(callback)

    def register_notification(self, callback):
        assert self.is_running_tests
        self.registered_notifications.append(callback)

    def debug(self, msg):
        assert self.is_running_tests
        self.logger.debug(msg)

    def info(self, msg):
        assert self.is_running_tests
        self.logger.info(msg)

    def notice(self, msg):
        assert self.is_running_tests
        self.logger.info(msg)

    def warning(self, msg):
        assert self.is_running_tests
        self.logger.warning(msg)

    def error(self, msg):
        assert self.is_running_tests
        self.logger.error(msg)

    def engine_run_init(self):
        for callback in self.registered_inits:
            callback()

    def engine_run_config(self, conf):
        for callback in self.registered_configs:
            callback(conf)

    def engine_read_metrics(self):
        for callback in self.registered_reads:
            callback()

    def engine_run_shutdowns(self):
        for callback in self.registered_shutdowns:
            callback()

    def values_class(self):
        # pylint: disable=too-few-public-methods
        class PluginData(object):
            # pylint: disable=redefined-builtin
            # pylint: disable=no-self-argument,too-many-arguments
            # We have to use 'type' to match collectd
            # need self2 b/c inner class
            def __init__(self2, host=None, plugin=None, plugin_instance=None,
                         time=None, type=None, type_instance=None, meta=None,
                         interval=None, values=None):
                if not meta:
                    meta = {}
                self2.host = host
                self2.plugin = plugin
                self2.plugin_instance = plugin_instance
                self2.time = time
                self2.type = type
                self2.type_instance = type_instance
                if values:
                    self2.values = values
                else:
                    self2.values = []
                self2.interval = interval
                self2.meta = meta

        class InnerValues(PluginData):
            # pylint: disable=no-self-argument
            def dispatch(self2):
                self.dispatched_values.append(self2)

            # pylint: disable=no-self-argument
            def write(self2):
                self.write_values.append(self2)

            # pylint: disable=no-self-argument
            def __str__(self2):
                ret = ""
                if self2.host is not None:
                    ret += "[host=%s]" % self2.host
                if self2.plugin is not None:
                    ret += "[plugin=%s]" % self2.plugin
                if self2.plugin_instance is not None:
                    ret += "[plugin_instance=%s]" % self2.plugin_instance
                if self2.time is not None:
                    ret += "[time=%s]" % self2.time
                if self2.type is not None:
                    ret += "[type=%s]" % self2.type
                if self2.type_instance is not None:
                    ret += "[type_instance=%s]" % self2.type_instance
                for val in self2.values:
                    ret += "[val=%s]" % val
                return ret

        return InnerValues


INSTANCE = DummyCollectd()

# pylint: disable=invalid-name
register_init = INSTANCE.register_init

# pylint: disable=invalid-name
register_config = INSTANCE.register_config

# pylint: disable=invalid-name
register_read = INSTANCE.register_read

# pylint: disable=invalid-name
register_flush = INSTANCE.register_flush

# pylint: disable=invalid-name
register_shutdown = INSTANCE.register_shutdown

# pylint: disable=invalid-name
register_log = INSTANCE.register_log

# pylint: disable=invalid-name
debug = INSTANCE.debug

# pylint: disable=invalid-name
info = INSTANCE.info

# pylint: disable=invalid-name
notice = INSTANCE.notice

# pylint: disable=invalid-name
warning = INSTANCE.warning

# pylint: disable=invalid-name
error = INSTANCE.error

# pylint: disable=invalid-name
Values = INSTANCE.values_class()

register_notification = INSTANCE.register_notification


# pylint: disable=too-few-public-methods
class Config(object):
    def __init__(self, parent=None, key="", values=None, children=None):
        if not children:
            children = []
        if not values:
            values = []
        self.parent = parent
        self.key = key
        self.values = values
        self.children = children
