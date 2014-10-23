# Copyright (C) 2013 SignalFx, Inc.

import logging
import os
import sys
import json
import copy
try:
    import httplib
    import urlparse
    from urllib import urlencode
    use_strict_in_py2 = True
except ImportError:
    import http.client
    import urllib.parse
    httplib = http.client
    urlparse = urllib.parse
    urlencode = urlparse.urlencode
    use_strict_in_py2 = False

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

def get_aws_instance_id(timeout=10):
    conn = httplib.HTTPConnection("169.254.169.254", 80, strict=True, timeout=timeout)
    conn.request("GET", "/latest/meta-data/instance-id")
    resp = conn.getresponse()
    if resp.status == 200:
        return resp.read()
    else:
        raise Exception("Unable to find instance ID from endpoint")


class DataPoint(object):
    def __init__(self, source, metric, value, ds_type, timestamp=0, dimensions=None):
        if dimensions is None:
            dimensions = {}
        self.source = source
        self.metric = metric
        self.value = value
        self.ds_type = ds_type
        self.timestamp = timestamp
        self.dimensions = dimensions

    def getDimensions(self):
        ret = {}
        if self.source is not None:
            ret['sf_source'] = self.source
        ret.update(self.dimensions)
        return ret

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
                conn_function = httplib.HTTPSConnection
            else:
                conn_function = httplib.HTTPConnection
            args = [self.host, self.port]
            kwargs = {'timeout': self.timeout}
            if use_strict_in_py2:
                kwargs['strict'] = True

            logging.info("Connecting to %s/%s", args, kwargs)
            self.conn = conn_function(*args, **kwargs)

    def connected(self):
        """Tells whether this instance is connected to the remote service."""
        return self.conn is not None

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
                for res in json.loads(result.decode("utf-8")):
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
        if self.conn is not None:
            self.conn.close()
        self.conn = None

    def tagSource(self, source_name, tags_to_add):
        sources = self.getSourcesFromName(source_name)
        if len(sources) == 0:
            return
        try:
            for source in sources:
                postBody = copy.copy(tags_to_add)
                for key, value in tags_to_add.items():
                    if key in source and source[key] == value:
                        del postBody[key]
                if len(postBody) == 0:
                    continue
                self.connect()
                if self.connected():
                    self.conn.request("POST", "/source/%s" % source['sf_id'], json.dumps(postBody),
                                      {"Content-type": "application/json",
                                       "X-SF-TOKEN": self.auth_token,
                                       "User-Agent": self.userAgent()})
                    resp = self.conn.getresponse()
                    if resp.status != 200:
                        logging.warning("Unexpected status of %d", resp.status)
                        self.disconnect()
                        return False
                    return True
                else:
                    logging.warning("Unable to connect to tag source name!")
        except Exception as e:
            logging.exception("Exception tagging sources: %s", e)
            self.disconnect()

    def getSourcesFromName(self, source_name):
        try:
            self.connect()
            if self.connected():
                params = urlencode({'query': 'sf_source:' + source_name})
                self.conn.request("GET", '/source?' + params, '',
                                  {"Content-type": "application/json",
                                   "X-SF-TOKEN": self.auth_token,
                                   "User-Agent": self.userAgent()})
                resp = self.conn.getresponse()
                if resp.status != 200:
                    logging.warning("Unexpected status of %d", resp.status)
                    self.disconnect()
                    return []
                m = json.loads(resp.read().decode("utf-8").strip())
                return m['rs']
            else:
                logging.warning("Unable to connect to get source IDs!")
                return []
        except Exception as e:
            logging.exception("Exception getting sources: %s", e)
            self.disconnect()
            return []

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
                if resp.status != 200:
                    logging.warning("Unexpected status of %d", resp.status)
                    self.disconnect()
                    return False
                result = resp.read().strip()
                if json.loads(result.decode("utf-8")) != "OK":
                    logging.warning("Unexpected body data of %s", result)
                    self.disconnect()
                    return False
                return True

            else:
                logging.warning("Unable to connect to send datapoints!")
        except Exception as e:
            logging.exception("Exception adding points %s", e)
            self.disconnect()

    def addDatapointsV2(self, datapoints):
        try:
            self.connect()
            if self.connected():
                postObj = {}
                for dp in datapoints:
                    s = {"metric": dp.metric,
                         "value": dp.value,
                         "dimensions": dp.getDimensions(),
                    }
                    if dp.timestamp != 0:
                        s['timestamp'] = dp.timestamp
                    objKey = dp.ds_type.lower()
                    if objKey not in postObj:
                        postObj[objKey] = []
                    postObj[objKey].append(s)
                postBody = json.dumps(postObj)
                logging.warning("Body is %s", postBody)
                self.conn.request("POST", "/v2_datapoint", postBody,
                                  {"Content-type": "application/json",
                                   "X-SF-TOKEN": self.auth_token,
                                   "User-Agent": self.userAgent()})
                resp = self.conn.getresponse()
                if resp.status != 200:
                    logging.warning("Unexpected status of %d body=%s", resp.status, resp.read().strip())
                    self.disconnect()
                    return False
                result = resp.read().strip()
                if json.loads(result.decode("utf-8")) != "OK":
                    logging.warning("Unexpected body data of %s", result)
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
    parser.add_argument('--tag', default=None, help='Tag to add to the source')
    parser.add_argument('--type', default="GAUGE", help='Type of metric to send')
    parser.add_argument('--value', default=time.time(), help='Value to send')
    parser.add_argument('--version', default=1, help='Version to use')

    parser.add_argument('auth_token', help="Which auth token to use")

    args = parser.parse_args()
    w = DatapointUploader(args.auth_token, args.url)
    if args.version == 1:
        dps = [DataPoint(args.source, args.metric, args.value, args.type)]
        assert(w.registerMultipleSeries(dps))
        print ("Result of add datapoints: " + str(w.addDatapoints(dps)))
    else:
        dps = [DataPoint(None, args.metric, args.value, args.type, dimensions={"from":"datapointuploader_6"})]
        print ("Result of add datapoints: " + str(w.addDatapointsV2(dps)))
    if args.tag is not None:
        w.tagSource(args.source, {"test_tag": args.tag})
