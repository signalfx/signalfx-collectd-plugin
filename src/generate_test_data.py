#! /usr/bin/env python

import json
import random
import subprocess
import sys
import time

hosts = ["rest_server1", "rest_server2", "rest_server3", "rest_server4", "rest_server5", "rest_server6"]
azs = ["us_east", "us_east", "us_west", "us_west", "us_west", "us_west"]
metric_types = ["counter", "gauge", "cumulative_counter"]
metrics = ["num_calls", "num_datapoints", "total_latency_ms"]
customers = ["acme corp", "wayne enterprises", "stark industries", "gringotts bank llc"]

i = 0

while True:
    for i in range(len(hosts) * len(metric_types) * len(customers)):
        i_host = i % len(hosts)
        i_metric_type = i % len(metric_types)
        i_customer = i % len(customers)
        host = hosts[i_host]
        az = azs[i_host]
        metric_type = metric_types[i_metric_type]
        customer = customers[i_customer]

        dim = {"host": host, "az": az, "customer": customer, "metric_type": metric_type}
        api_count = random.randint(0, 10 * (i_customer + 1))
        data_count = api_count * random.randint(10, 30)
        latency_mul = 1
        if i_host >= 4:
            latency_mul = i_host - 2
        latency_total = data_count * random.randint(50, 80) * latency_mul
        subprocess.Popen(["python", "datapointuploader.py",
                      "--version", "2",
                      "--url", "http://lb-lab3--bbaa.int.signalfuse.com:8080",
                      "--metric", "md_demo.num_calls",
                      "--dim", json.dumps(dim),
                      "--type", "COUNTER",
                      "--value", str(api_count),
                      "JVS-5cLAW0haSykDzpWIMw"])
        subprocess.Popen(["python", "datapointuploader.py",
                      "--version", "2",
                      "--url", "http://lb-lab3--bbaa.int.signalfuse.com:8080",
                      "--metric", "md_demo.num_datapoints",
                      "--dim", json.dumps(dim),
                      "--type", "COUNTER",
                      "--value", str(data_count),
                      "JVS-5cLAW0haSykDzpWIMw"])
        subprocess.Popen(["python", "datapointuploader.py",
                      "--version", "2",
                      "--url", "http://lb-lab3--bbaa.int.signalfuse.com:8080",
                      "--metric", "md_demo.total_latency_ms",
                      "--dim", json.dumps(dim),
                      "--type", "COUNTER",
                      "--value", str(latency_total),
                      "JVS-5cLAW0haSykDzpWIMw"])
    time.sleep(5)
