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
import unittest

class DatapointUploaderTestCase(unittest.TestCase):
    def test_create(self):
        d = datapointuploader.DatapointUploader('', 'http://test.com')
