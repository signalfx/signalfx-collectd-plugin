import SimpleHTTPServer
import SocketServer
import pretend_collectd as collectd

import sys

sys.modules["collectd"] = collectd

import json
import logging

logging.basicConfig()
import threading
import urlparse

log = logging.getLogger(__name__)

import datapointuploader
import collectdtosf

assert collectdtosf is not None, "Dummy assert so lint thinks the module is used"
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


class SignalFxSimpleHTTPRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler):
    datapoints = []
    requestSemaphore = threading.Semaphore(0)

    # noinspection PyShadowingBuiltins
    def log_message(self, format, *args):
        log.debug("%s - - [%s] %s\n" %
                  (self.client_address[0],
                   self.log_date_time_string(),
                   format % args))

    def do_POST(self):
        log.debug("Do post?")
        len_to_read = int(self.headers.get('Content-Length'))
        data = self.rfile.read(len_to_read)
        parsed_url = urlparse.urlparse(self.path)
        if parsed_url.path == '/metric':
            self.processMetric(data)
        else:
            self.processDatapoints(data)


    def processMetric(self, data):
        log.debug("processMetric")
        data = json.loads(data)
        self.send_response(200)
        self.end_headers()
        res = [{'code': 409} for i in range(len(data))]
        self.wfile.write(json.dumps(res))
        [self.requestSemaphore.release() for i in range(len(data))]

    def processDatapoints(self, data):
        log.debug("processDatapoints")
        datapoints = []
        is_this_valid_json = ""
        # this is horid, and laws, but works for unit tests
        while len(data) > 0:
            try:
                datapoints.append(json.loads(is_this_valid_json))
                is_this_valid_json = ""
            except ValueError:
                is_this_valid_json += data[0]
                data = data[1:]

        datapoints.append(json.loads(is_this_valid_json))
        log.debug("Extending by %d", len(datapoints))
        self.datapoints.extend(datapoints)
        self.send_response(200)
        self.end_headers()
        res = 'OK'
        self.wfile.write(json.dumps(res))
        [self.requestSemaphore.release() for i in range(len(datapoints))]
        log.debug("Done process?")


class CollectdTestCase(unittest.TestCase):
    def setUp(self):
        Handler = SignalFxSimpleHTTPRequestHandler
        self.httpd = SocketServer.TCPServer(("", 0), Handler)
        httpd_thread = threading.Thread(target=self.httpd.serve_forever)
        httpd_thread.start()
        log.info("Setup thread")

    def tearDown(self):
        self.httpd.shutdown()
        for (shutdown_func, data) in collectd.shutdown_functions:
            shutdown_func(data)

    def test_collectd_flow(self):
        url = "http://%s:%d" % self.httpd.socket.getsockname()
        log.debug("test_collectd_flow")

        (handler, types_db) = tempfile.mkstemp('signalfx-tests')
        config = collectd.Config(
            [collectd.Config(key='url', values=[url]),
             collectd.Config(key='types_db', values=[types_db]),
            collectd.Config(key='replacement_regex', values=["a", "b"])]
            )
        for (config_func, data) in collectd.config_functions:
            config_func(config, data)

        for (init_func, data) in collectd.init_functions:
            init_func(data)

        collectd.Values(host='', plugin='', type='atype', type_instance='', interval=4,
                        values=[3]).dispatch()

        log.debug("Getting Sempa")
        # (1) register (2) get datapoint
        [SignalFxSimpleHTTPRequestHandler.requestSemaphore.acquire() for i in range(2)]
        log.debug("Sempa phase one done")

        assert len(SignalFxSimpleHTTPRequestHandler.datapoints) == 1
        assert SignalFxSimpleHTTPRequestHandler.datapoints[0]['metric'] == 'collectd.atype'
        assert SignalFxSimpleHTTPRequestHandler.datapoints[0]['value'] == 3.0

        for (read_func, data) in collectd.read_functions:
            read_func(data)

        # get all 6 metrics and their registration
        [SignalFxSimpleHTTPRequestHandler.requestSemaphore.acquire() for _ in xrange(12)]
        assert len(SignalFxSimpleHTTPRequestHandler.datapoints) == 7
        assert [v for v in SignalFxSimpleHTTPRequestHandler.datapoints if
                v['metric'] == 'collectd.collectd-signalfx.metrics_written.derive'][0]['value'] == 1

        for (shutdown_func, data) in collectd.shutdown_functions:
            shutdown_func(data)
