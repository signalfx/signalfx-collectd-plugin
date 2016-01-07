import logging
import time

from nose.tools import assert_equals

import aggregator
import collectd_dogstatsd
import dogstatsd
import dummy_collectd

dummy_collectd.INSTANCE.is_running_tests = True
logging.basicConfig(level=logging.DEBUG)
dummy_collectd.INSTANCE.init_logging()


def make_config():
    cfg = dummy_collectd.Config(
        children=[
            dummy_collectd.Config(key="DogStatsDPort",
                                  values=["1234"]),
            dummy_collectd.Config(key="collectdsend",
                                  values=["true"]),
        ]
    )
    return cfg


class TestModuleSetup(object):
    def __init__(self):
        self.collectd_engine = None
        self.dog_module = None

    def setUp(self):
        self.collectd_engine = dummy_collectd.DummyCollectd(
            is_running_tests=True)
        self.collectd_engine.init_logging()
        self.dog_module = collectd_dogstatsd.DogstatsDCollectD(
            self.collectd_engine, register=True)
        self.dog_module.config.udp_timeout = .1
        aggregator.time = self.time
        self.current_time = time.time()
        self.collectd_engine.engine_run_config(make_config())
        self.collectd_engine.engine_run_init()

    def tearDown(self):
        self.collectd_engine.engine_run_shutdowns()
        self.collectd_engine = None
        self.dog_module = None
        aggregator.time = time.time()

    def time(self):
        return self.current_time

    def test_errorlog(self):
        self.collectd_engine.engine_run_config(dummy_collectd.Config())
        logger = collectd_dogstatsd.Logger(dummy_collectd)
        logger.verbose_logging = True
        logger.verbose("verbose")
        logger.info("info")
        logger.notice("notice")
        logger.warning("warning")
        logger.error("error")

    def _value_setup(self, metrics, expected):
        self.dog_module.log.verbose_logging = True
        for metric in metrics:
            self.dog_module.server.metrics_aggregator.submit_packets(metric)

        self.current_time += dogstatsd.DOGSTATSD_AGGREGATOR_BUCKET_SIZE
        self.collectd_engine.engine_read_metrics()
        metrics = self.collectd_engine.dispatched_values

        print [s.__str__() for s in metrics]
        assert_equals(len(metrics), len(expected))
        for idx, exp in enumerate(expected):
            assert_equals(metrics[idx].type_instance, exp[0])
            assert_equals(metrics[idx].values, exp[1])
            assert_equals(metrics[idx].type, exp[2])
            assert_equals(metrics[idx].plugin_instance, exp[3])

    def test_gauge(self):
        self._value_setup(["fuel.level:0.5|g"],
                          [["fuel.level", [0.5], "gauge", ""]])

    def test_counter(self):
        self._value_setup(["page.views:1|c"],
                          [["page.views", [1], "absolute", ""]])

    def test_histogram(self):
        self._value_setup(
            ["song.length:240|h|@0.5"],
            [
                ["song.length.max", [240], "gauge", ""],
                ["song.length.median", [240], "gauge", ""],
                ["song.length.avg", [240], "gauge", ""],
                ["song.length.count", [2], "absolute", ""],
                ["song.length.95percentile", [240], "gauge", ""],
            ])

    def test_timer(self):
        self._value_setup(
            ["page.loadtime:1234|ms"],
            [
                ["page.loadtime.max", [1234], "gauge", ""],
                ["page.loadtime.median", [1234], "gauge", ""],
                ["page.loadtime.avg", [1234], "gauge", ""],
                ["page.loadtime.count", [1], "absolute", ""],
                ["page.loadtime.95percentile", [1234], "gauge", ""],
            ])

    def test_sets(self):
        self._value_setup(
            ["users.uniques:1234|s"],
            [
                ["users.uniques", [1], "gauge", ""],
            ])

    def test_counter_tags(self):
        self._value_setup(
            ["users.online:1|c|#country:china"],
            [
                ["users.online", [1], "absolute", "[country=china]"],
            ])

    def test_counter_sample_tags(self):
        self._value_setup(
            ["users.online:1|c|@0.5|#country:china"],
            [
                ["users.online", [2], "absolute", "[country=china]"],
            ])
