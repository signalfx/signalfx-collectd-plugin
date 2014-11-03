CollectD Plugin for SignalFuse
==============================

Installation of collectd via apt-get
------------------------

1. Install colletctd via apt-get

    ```
$ sudo apt-get install collectd
    ```

Supported python versions
-------------------------

The plugin currently only supports python 2.7+ and does
not support 3.0

Configuration
-------------

1. Copy over the signalfx collectd repository to a local directory
    ```
$ git clone https://github.com/signalfx/signalfx-collectd-plugin /opt/signalfx-collectd-plugin
    ```

2. Create a signalfx collectd conf 
    ```
$ cp /opt/signalfx-collectd-plugin/signalfx-collectd-plugin.conf /etc
    ```

3. Modify collectd-signalfx.conf and replace ###API_TOKEN### with your API token

4. Start collectd:
    ```
    sudo /etc/init.d/collectd start
    ```

5. Check the following files to debug the install:
   ```
   /var/log/collectd.log
   /var/log/signalfx-collectd-plugin.log
   ```

Build status
------------
[![Build Status](https://travis-ci.org/signalfx/collectd-signalfx.svg?branch=master)](https://travis-ci.org/signalfx/collectd-signalfx)
