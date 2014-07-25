import imp

# Setup collectd module
collectd = imp.new_module("collectd")
def register_init(init_func, data):
    pass
def register_config(config_func, data):
    pass
def register_shutdown(shutdown_func, data):
    pass
collectd.register_init = register_init
collectd.register_config = register_config
collectd.register_shutdown= register_shutdown

import sys
sys.modules["collectd"] = collectd

import datapointuploader, collectdtosf
from datapointuploader import DataPoint
import unittest

class DatapointUploaderTestCase(unittest.TestCase):
    def test_datapoint_uploader(self):
        d = datapointuploader.DatapointUploader('', 'https://api.signalfuse.com')
        d.connect()
        assert d.connected()
        dps = [DataPoint('source', 'metric', 3, 'GAUGE')]
        res = d.addDatapoints(dps)
        assert res is False
