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
import get_all_auth_tokens
from datapointuploader import DataPoint
import unittest
import tempfile

class DatapointUploaderTestCase(unittest.TestCase):
    def test_datapoint_uploader(self):
        d = datapointuploader.DatapointUploader('', 'https://api.signalfuse.com')
        d.connect()
        assert d.connected()
        dps = [DataPoint('source', 'metric', 3, 'GAUGE')]
        res = d.addDatapoints(dps)
        assert res is False


class AuthTokenReplaceTestCase(unittest.TestCase):
    def test_replaceInFile(self):
        (handler, filename) = tempfile.mkstemp('signalfx-tests')
        with open(filename, 'w') as f:
            f.write("""hello
            world
            APIToken "test"
            """)
        get_all_auth_tokens.replace_in_file(filename, 'APIToken "(.*)"', 'APIToken "abce"')
        with open(filename) as f:
            new_contents = f.read()
        assert new_contents == """hello
            world
            APIToken "abce"
            """
