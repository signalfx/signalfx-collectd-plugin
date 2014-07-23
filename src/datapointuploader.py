# Copyright (C) 2013 SignalFx, Inc.

import logging
import os
import sys
import json
try:
    import httplib
    import urlparse
except ImportError:
    import http.client
    import urllib.parse
    httplib = http.client
    urlparse = urllib.parse

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))


class DataPoint(object):
    def __init__(self, source, metric, value, ds_type, timestamp=0):
        self.source = source
        self.metric = metric
        self.value = value
        self.ds_type = ds_type
        self.timestamp = timestamp

    def __str__(self):
        return "%s/%s/%s/%s/%d" % (
            self.source, self.metric, str(self.value), self.ds_type, self.timestamp)


class DatapointUploader():
    def __init__(self, auth_token, url, timeout=60, user_agent_name="DatapointUploader",
                 user_agent_version=.1):
        parsed_url = urlparse.urlparse(url)
        if parsed_url.hostname is None or (parsed_url.scheme not in set(['http', 'https'])):
            raise Exception(
                'The url is not correct. Please check it: {0}'.format(url))
        self.host = parsed_url.hostname
        self.https = (parsed_url.scheme == 'https')
        port = parsed_url.port
        if port:
            self.port = int(port)
        else:
            self.port = 80
            if parsed_url.scheme == 'https':
                self.port = 443

        self.auth_token = auth_token
        self.timeout = timeout
        self.conn = None
        self.user_agent_version = user_agent_version
        self.user_agent_name = user_agent_name

    def __str__(self):
        return 'DatapointUploader(%s:%d)' % (self.host, self.port)

    def userAgent(self):
        return "%s/%s" % (self.user_agent_name, self.user_agent_version)

    def connect(self):
        if not self.connected():
            if self.https:
                logging.debug('https Connecting to %s...', self)
                self.conn = httplib.HTTPSConnection(self.host, self.port, strict=True,
                                                   timeout=self.timeout)
            else:
                logging.debug('http Connecting to %s...', self)
                self.conn = httplib.HTTPConnection(self.host, self.port, strict=True,
                                                   timeout=self.timeout)

    def connected(self):
        """Tells whether this instance is connected to the remote service."""
        return self.conn != None

    def registerMultipleSeries(self, all_series):
        assert (len(all_series) > 0)
        logging.info("Registering multiple series: %s",
                      ",".join([i.metric for i in all_series]))
        try:
            self.connect()
            if self.connected():
                body = []
                for item in all_series:
                    body.append({"sf_metric": item.metric, "sf_metricType": item.ds_type})
                postBody = json.dumps(body)
                self.conn.request("POST", "/metric?bulkupdate=true", postBody,
                                  {"Content-type": "application/json",
                                   "X-SF-TOKEN": self.auth_token,
                                   "User-Agent": self.userAgent()})
                resp = self.conn.getresponse()
                result = resp.read().strip()
                if resp.status != 200:
                    logging.warning("Unexpected status of %d body %s", resp.status, result)
                    self.disconnect()
                    return [False] * len(all_series)
                ret = []
                for res in json.loads(result):
                    if 'code' in res:
                        if int(res['code']) != 409: # Already exists
                            logging.debug("Unknown code for %s", res)
                            ret.append(False)
                        else:
                            ret.append(True)
                    else:
                        ret.append(True)
                return ret
            else:
                logging.warning("Unable to connect to register datapoints!")
        except Exception as e:
            logging.exception("Exception adding points %s", e)
            self.disconnect()
        return [False] * len(all_series)

    def disconnect(self):
        if self.conn != None:
            self.conn.close()
        self.conn = None

    def addDatapoints(self, datapoints):
        try:
            self.connect()
            if self.connected():
                postBody = ""
                for dp in datapoints:
                    s = {"source": dp.source, "metric": dp.metric,
                         "value": dp.value}
                    if dp.timestamp != 0:
                        s['timestamp'] = dp.timestamp
                    postBody += json.dumps(s)
                self.conn.request("POST", "/datapoint", postBody,
                                  {"Content-type": "application/json",
                                   "X-SF-TOKEN": self.auth_token,
                                   "User-Agent": self.userAgent()})
                resp = self.conn.getresponse()
                result = resp.read().strip()
                if json.loads(result) != "OK":
                    logging.warning("Unexpected body data of %s", result)
                    self.disconnect()
                    return False
                if resp.status != 200:
                    logging.warning("Unexpected status of %d", resp.status)
                    self.disconnect()
                    return False
                return True

            else:
                logging.warning("Unable to connect to send datapoints!")
        except Exception as e:
            logging.exception("Exception adding points %s", e)
            self.disconnect()


if __name__ == '__main__':
    import argparse, time
    parser = argparse.ArgumentParser(
        description='Test sending a test datapoint to SignalFX.')
    parser.add_argument('--url', default='https://api.signalfuse.com', help='URL Endpoint.')

    parser.add_argument('--source', default="DatapointUploaderSource", help='Source name to send')
    parser.add_argument('--metric', default="DatapointUploaderMetric", help='Metric name to send')
    parser.add_argument('--type', default="GAUGE", help='Type of metric to send')
    parser.add_argument('--value', default=time.time(), help='Value to send')

    parser.add_argument('auth_token', help="Which auth token to use")

    args = parser.parse_args()
    w = DatapointUploader(args.auth_token, args.url)
    dps = [DataPoint(args.source, args.metric, args.value, args.type)]
    assert(w.registerMultipleSeries(dps))
    print ("Result of add datapoints: " + str(w.addDatapoints(dps)))
