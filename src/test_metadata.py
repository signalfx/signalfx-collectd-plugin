import logging
import time

from nose.tools import assert_equals

import dummy_collectd

dummy_collectd.INSTANCE.is_running_tests = True
logging.basicConfig(level=logging.DEBUG)
dummy_collectd.INSTANCE.init_logging()

import signalfx_metadata as sfx


class TestUtilizationFactory(object):
    def __init__(self):
        self.collectd_engine = None
        self.utilization_factory = None
        self.val = 0
        self.time = time.time()

    def setUp(self):
        self.collectd_engine = dummy_collectd.DummyCollectd(
            is_running_tests=True)
        self.collectd_engine.init_logging()
        self.utilization_factory = sfx.UtilizationFactory()
        sfx.collectd = self.collectd_engine
        sfx.DEBUG = True

    def tearDown(self):
        self.collectd_engine.engine_run_shutdowns()
        self.collectd_engine = None
        self.utilization_factory = None

    def _gen(self, type_instances, plugin, type, plugin_instances=[""],
             missing=0, values=1, increment_time=True):
        self.val += 1
        metrics = []
        if increment_time is True:
            self.time += 10.0
        for type_instance in type_instances[:len(type_instances) - missing]:
            for plugin_instance in plugin_instances:
                v = []
                for i in range(values):
                    v.append(self.val)
                metrics.append(dummy_collectd.
                               Values(plugin=plugin,
                                      plugin_instance=plugin_instance,
                                      time=self.time, type=type,
                                      type_instance=type_instance,
                                      interval=10,
                                      values=v))
        return metrics

    def gen_memory(self, missing=0, increment_time=True):
        for m in self._gen(
                ['used', 'cached', 'buffered', 'slab_recl', 'slab_unrecl',
                 'free'],
                "memory", "memory", missing=missing,
                increment_time=increment_time):
            self.utilization_factory.write(m)
        self.utilization_factory.read()

    def gen_cpu(self, missing=0, increment_time=True):
        for m in self._gen(
                ['idle', 'steal', 'wait', 'system', 'user', 'nice',
                 'interrupt', 'softirq'],
                "aggregation", "cpu", plugin_instances=["cpu-average"],
                missing=missing, increment_time=increment_time):
            print m
            self.utilization_factory.write(m)
        self.utilization_factory.read()

    def gen_df(self, missing=0, missing_plugin_instances=0,
               additional_plugin_instances=[], increment_time=True):
        for m in self._gen(['reserved', 'free', 'used'],
                           "df", "df_complex", missing=missing,
                           plugin_instances=(["opt", "bin", "blarg"][:3 -
                                             missing_plugin_instances] +
                                             additional_plugin_instances),
                           increment_time=increment_time):
            self.utilization_factory.write(m)
        self.utilization_factory.read()

    def gen_disk(self, missing=0, increment_time=True):
        for m in self._gen([''], "disk", "disk_ops",
                           plugin_instances=["sda", "hda", "sdb"][
                                            :3 - missing], values=2,
                           increment_time=increment_time):
            self.utilization_factory.write(m)
        self.utilization_factory.read()

    def gen_network(self, missing=0, increment_time=True):
        for m in self._gen([''], "disk", "disk_ops",
                           plugin_instances=["eth0", "eth1", "lo"][
                                            :3 - missing], values=2,
                           increment_time=increment_time):
            self.utilization_factory.write(m)
        self.utilization_factory.read()

    def test_cpu_utilization(self):
        self.gen_cpu()
        assert_equals(len(self.collectd_engine.dispatched_values), 0)
        self.gen_cpu()
        assert_equals(len(self.collectd_engine.dispatched_values), 1)
        self.gen_cpu(missing=1)
        assert_equals(len(self.collectd_engine.dispatched_values), 1)
        self.utilization_factory.read()
        assert_equals(len(self.collectd_engine.dispatched_values), 1)
        self.gen_cpu(increment_time=False)  # metric should not be dropped
        self.gen_cpu(increment_time=False)  # metric should be dropped
        self.gen_cpu(increment_time=False)  # metric should be dropped
        assert_equals(len(self.collectd_engine.dispatched_values), 2)

    def test_memory_utilization(self):
        self.gen_memory()
        assert_equals(len(self.collectd_engine.dispatched_values), 0)
        self.gen_memory()
        assert_equals(len(self.collectd_engine.dispatched_values), 0)
        self.gen_memory()
        assert_equals(len(self.collectd_engine.dispatched_values), 3)
        self.gen_memory(missing=1)
        assert_equals(len(self.collectd_engine.dispatched_values), 3)
        self.utilization_factory.read()
        assert_equals(len(self.collectd_engine.dispatched_values), 3)
        self.gen_memory(increment_time=False)  # value should not be dropped
        self.gen_memory(increment_time=False)  # value should be dropped
        self.gen_memory(increment_time=False)  # value should be dropped
        assert_equals(len(self.collectd_engine.dispatched_values), 4)

    def test_df_utilizaton(self):
        self.gen_df()
        assert_equals(len(self.collectd_engine.dispatched_values), 3)
        self.gen_df()
        assert_equals(len(self.collectd_engine.dispatched_values), 6,
                      "will be two summary and one regular")
        self.gen_df(missing=1)
        # two of these are disk.summary_utilization
        assert_equals(len(self.collectd_engine.dispatched_values), 8)
        self.utilization_factory.read()
        assert_equals(len(self.collectd_engine.dispatched_values), 8)
        for v in self.collectd_engine.dispatched_values:
            assert_equals(v.values[0], 50.0)

        # test the probation plugin_instances
        self.gen_df(missing_plugin_instances=1)
        assert_equals(len(self.collectd_engine.dispatched_values), 10)
        for v in self.collectd_engine.dispatched_values:
            assert_equals(v.values[0], 50.0)
        self.gen_df(missing_plugin_instances=1)
        assert_equals(len(self.collectd_engine.dispatched_values), 12)
        for v in self.collectd_engine.dispatched_values:
            assert_equals(v.values[0], 50.0)
        self.gen_df(missing_plugin_instances=1)
        assert_equals(len(self.collectd_engine.dispatched_values), 15)
        for v in self.collectd_engine.dispatched_values:
            assert_equals(v.values[0], 50.0)

        self.gen_df(increment_time=False)  # metric should not be dropped
        self.gen_df(increment_time=False)  # metric should be dropped
        self.gen_df(increment_time=False)  # metric should be dropped

        # assert_equals(len(self.collectd_engine.dispatched_values), 16)

        # test the addition of plugin_instances
        self.gen_df()
        assert_equals(len(self.collectd_engine.dispatched_values), 19)
        for v in self.collectd_engine.dispatched_values:
            assert_equals(v.values[0], 50.0)

    def test_disk_total(self):
        self.gen_disk()
        assert_equals(len(self.collectd_engine.dispatched_values), 0)
        self.gen_disk()
        assert_equals(len(self.collectd_engine.dispatched_values), 0)
        self.gen_disk()
        assert_equals(len(self.collectd_engine.dispatched_values), 3)
        self.gen_disk()
        assert_equals(len(self.collectd_engine.dispatched_values), 4)
        self.gen_disk(missing=1)
        assert_equals(len(self.collectd_engine.dispatched_values), 4)
        self.utilization_factory.read()
        assert_equals(len(self.collectd_engine.dispatched_values), 5)
        prev = self.collectd_engine.dispatched_values[3]
        last = self.collectd_engine.dispatched_values[4]
        # should be 4 more instead of 6
        assert_equals(prev.values[0] + 4, last.values[0])
        self.gen_disk(increment_time=False)  # metric should be dropped
        self.gen_disk(increment_time=False)  # metric should be dropped
        self.gen_disk(increment_time=False)  # value should be dropped
        assert_equals(len(self.collectd_engine.dispatched_values), 5)

    def test_network_total(self):
        self.gen_network()
        assert_equals(len(self.collectd_engine.dispatched_values), 0)
        self.gen_network()
        assert_equals(len(self.collectd_engine.dispatched_values), 0)
        self.gen_network()
        assert_equals(len(self.collectd_engine.dispatched_values), 3)
        self.gen_network()
        assert_equals(len(self.collectd_engine.dispatched_values), 4)
        self.gen_network(missing=1)
        assert_equals(len(self.collectd_engine.dispatched_values), 4)
        self.utilization_factory.read()
        assert_equals(len(self.collectd_engine.dispatched_values), 5)
        prev = self.collectd_engine.dispatched_values[3]
        last = self.collectd_engine.dispatched_values[4]
        # should be 4 more instead of 6
        assert_equals(prev.values[0] + 4, last.values[0])
        self.gen_network(increment_time=False)  # metric should be dropped
        self.gen_network(increment_time=False)  # metric should be dropped
        self.gen_network(increment_time=False)  # metric should be dropped
        assert_equals(len(self.collectd_engine.dispatched_values), 5)


t = TestUtilizationFactory()
for x in dir(t):
    if "test_" in x:
        methodToCall = getattr(t, x)
        t.setUp()
        result = methodToCall()
        t.tearDown()
