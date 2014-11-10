#! /usr/bin/env python

import json
import random
import subprocess
import time

hosts = ["host1", "host2", "host3"]
instances = ["instance1", "instance2"]
users = ["user1", "user2", "user3", "user4"]

i = 0

while True:
    for i in range(len(hosts) * len(instances) * len(users)):
        i_host = i % len(hosts)
        i_instance = i % len(instances)
        i_user = i % len(users)
        host = hosts[i_host]
        instance = instances[i_instance]
        user = users[i_user]

        dim = {"host": host, "instance": instance, "user": user}
        subprocess.Popen(["python", "datapointuploader.py",
                      "--version", "2",
                      "--url", "http://lb-lab3--bbaa.int.signalfuse.com:8080",
                      "--metric", "mdtestmetric",
                      "--dim", json.dumps(dim),
                      "--value", str(i_host * 100 + i_instance * 10 + i_user + random.randint(10, 20)),
                      "JVS-5cLAW0haSykDzpWIMw"])
    time.sleep(5)
