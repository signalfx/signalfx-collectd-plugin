# From https://github.com/DataDog/dd-agent/aggregator.py

"""
Simplified BSD License

Copyright (c) 2009, Boxed Ice <hello@boxedice.com>
Copyright (c) 2010-2015, Datadog <info@datadoghq.com>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice,
  this list of conditions and the following disclaimer.
* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.
* Neither the name of Boxed Ice nor the names of its contributors
  may be used to endorse or promote products derived from this software
  without specific prior written permission.
* Neither the name of Datadog nor the names of its contributors
  may be used to endorse or promote products derived from this software
  without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import threading

"""
A Python Statsd implementation with some datadog special sauce.
"""

# stdlib
import logging
import os
import select
import socket
import zlib

import simplejson as json

# project
from aggregator import MetricsBucketAggregator, DEFAULT_HISTOGRAM_AGGREGATES, \
    DEFAULT_HISTOGRAM_PERCENTILES


# urllib3 logs a bunch of stuff at the info level
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.WARN)
requests_log.propagate = True

log = logging.getLogger('dogstatsd')

# Dogstatsd constants in seconds
DOGSTATSD_FLUSH_INTERVAL = 10
DOGSTATSD_AGGREGATOR_BUCKET_SIZE = 10


WATCHDOG_TIMEOUT = 120
UDP_SOCKET_TIMEOUT = 5
# Since we call flush more often than the metrics aggregation interval, we should
#  log a bunch of flushes in a row every so often.
FLUSH_LOGGING_PERIOD = 70
FLUSH_LOGGING_INITIAL = 10
FLUSH_LOGGING_COUNT = 5
EVENT_CHUNK_SIZE = 50
COMPRESS_THRESHOLD = 1024


def serialize_metrics(metrics):
    serialized = json.dumps({"series": metrics})
    if len(serialized) > COMPRESS_THRESHOLD:
        headers = {'Content-Type': 'application/json',
                   'Content-Encoding': 'deflate'}
        serialized = zlib.compress(serialized)
    else:
        headers = {'Content-Type': 'application/json'}
    return serialized, headers


def serialize_event(event):
    return json.dumps(event)


class Server(object):
    """
    A statsd udp server.
    """

    def __init__(self, metrics_aggregator, host, port, forward_to_host=None, forward_to_port=None, timeout=UDP_SOCKET_TIMEOUT):
        self.host = host
        self.port = int(port)
        self.address = (self.host, self.port)
        self.metrics_aggregator = metrics_aggregator
        self.buffer_size = 1024 * 8
        self.start_has_finished = threading.Semaphore()
        self.shouldStop = threading.Event()
        self.running = threading.Event()
        self.socket = None
        self.timeout = timeout

        self.should_forward = forward_to_host is not None


        self.forward_udp_sock = None
        # In case we want to forward every packet received to another statsd server
        if self.should_forward:
            if forward_to_port is None:
                forward_to_port = 8125

            log.info("External statsd forwarding enabled. All packets received will be forwarded to %s:%s" % (forward_to_host, forward_to_port))
            try:
                self.forward_udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.forward_udp_sock.connect((forward_to_host, forward_to_port))
            except Exception:
                log.exception("Error while setting up connection to external statsd server")

    def start(self):
        try:
            self.start_has_finished.acquire()
            self._start()
        finally:
            self.socket.close()
            self.start_has_finished.release()

    def _start(self):
        """ Run the server. """
        # Bind to the UDP socket.
        # IPv4 only
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setblocking(0)
        try:
            self.socket.bind(self.address)
        except socket.gaierror:
            if self.address[0] == 'localhost':
                log.warning("Warning localhost seems undefined in your host file, using 127.0.0.1 instead")
                self.address = ('127.0.0.1', self.address[1])
                self.socket.bind(self.address)

        log.info('Listening on host & port: %s' % str(self.socket.getsockname()))

        # Inline variables for quick look-up.
        buffer_size = self.buffer_size
        aggregator_submit = self.metrics_aggregator.submit_packets
        sock = [self.socket]
        socket_recv = self.socket.recv
        select_select = select.select
        select_error = select.error
        timeout = self.timeout
        should_forward = self.should_forward
        forward_udp_sock = self.forward_udp_sock

        # Run our select loop.
        while not self.shouldStop.is_set():
            # print "Running is NOT clear ---- %s %s" % (self.running, self.running.isSet())
            try:
                ready = select_select(sock, [], [], timeout)
                if ready[0]:
                    message = socket_recv(buffer_size)
                    aggregator_submit(message)

                    if should_forward:
                        forward_udp_sock.send(message)
            except select_error, se:
                # Ignore interrupted system calls from sigterm.
                errno = se[0]
                if errno != 4:
                    raise
            except (KeyboardInterrupt, SystemExit):
                break
            except Exception:
                log.exception('Error receiving datagram')

    def stop(self):
        self.shouldStop.set()
        # print "STOP().  Will clear running %s %s" % (self.running, self.running.isSet())



def init(server_host, port, timeout=UDP_SOCKET_TIMEOUT, aggregator_interval=DOGSTATSD_AGGREGATOR_BUCKET_SIZE):
    """Configure the server and the reporting thread.
    """

    log.debug("Configuring dogstatsd")

    hostname = None

    aggregator = MetricsBucketAggregator(
        hostname,
        aggregator_interval,
        recent_point_threshold=None,
        formatter=None,
        histogram_aggregates=DEFAULT_HISTOGRAM_AGGREGATES,
        histogram_percentiles=DEFAULT_HISTOGRAM_PERCENTILES,
        utf8_decoding=True,
    )

    server = Server(aggregator, server_host, port, timeout=timeout)

    return server
