0.0.32 / 2017-06-19
===================

* Fix issue preventing host process info from being reported.

0.0.31 / 2017-06-19

* Configure alternate proc path
* Configure alternate etc path
* Fix logging of "Next Metadata Send" message

0.0.30 / 2017-03-25

* Fix memory leak related to cpu utilization metrics collection
* Upgrade to latest signalfx-python v1.0.16

0.0.29 / 2016-11-02

* Added python dependency six

0.0.28 / 2016-10-18

* Upgrade to latest signalfx-python v1.0.7
* Log outdated metrics instead of emitting them

0.0.27 / 2016-09-21

* Periodically check if the plugin is running on AWS

0.0.26 / 2016-09-08

* Add optional configuration to report cpu utilization on a per core basis

0.0.25 / 2016-08-03

* Upgrade to latest signalfx-python v1.0.4

0.0.24 / 2016-06-28

* no longer report gauge.sf.host-dpm as it was an instantaneous rate of change
  and comparisons with it were inaccurate.

0.0.23 / 2016-06-02

* upgrade to latest signalfx-python

0.0.21 / 2016-04-04

* send version information as dimensions on the plugin_uptime metric
* work around issue where collectd segfaults on shutdown when write callback
  is an instance method
* add way to turn off datapoints
* add dither to initial notifications

0.0.20 / 2016-03-31

* change memory.utilization to not include cached, bufferred or slab but just
  be used/total
* fix repetative logging when types.db.plugin isn't found

0.0.19 / 2016-03-25

* add ability for multiple endpoints

0.0.18 / 2016-03-21

* refactory utilizations
* add unit tests

0.0.17 / 2016-03-17

* quantize utilization metrics for better accuracy

0.0.16 / 2016-03-15

* fix bug where memory.utilization wasn't always reported

0.0.15 / 2016-03-11

* fix bug with summation metrics first points being wild
* detect intervals for each type of utilization data and emit on
  same schedule
* add AWSUniqueId if not present, and we're an AWS box

0.0.14 / 2016-03-09

* fix bug with utilization metrics not showing without DPM
* fix bug where plugin doesn't emit metrics on old collectds

0.0.13 / 2016-02-29

* add Utilization metrics behind flag defaulted to true
* update sf.host-response.max to include the timeout times

0.0.12 / 2016-01-15

* change uptime to plugin uptime
* quiet a few more top exceptions
* default timeout to 3 seconds

0.0.11 / 2016-01-07

* fix units issue on memory
* add metrics for max response time, send errors and dpm
* quiet top info when pids disappear
* steal hosts from other notifications even if we aren't the one sending them

0.0.10 / 2015-11-04

* add dogstatsd support if configured to do so

0.0.9 / 2015-10-26

* use self instead of os.getpid to get collectd version
* change how often we send metadata from only on startup to startup,
  one minute, hour and day, then per day from then on
* use psutil instead of top
* send in plugin version as plugin_instance

0.0.8 / 2015-10-02

* wait one interval before sending notifications
* url error parsing more resilient
* add back in logical cpus
* better linux version checking

0.0.7 / 2015-09-29

* Remove dependence on requests

0.0.6 / 2015-09-27

* Add interfaces notifcation
* Remove logical cpus
* prefix with host_
* support /etc/os-release for linux_version
* Send LargeNotifs if message too large for collectd

0.0.5 / 2015-09-25

* Use host from collectd for Top Info notification
* Add mem_total for physical memory in kb

0.0.4 / 2015-09-20

* Top on amazon linux and better error handling

0.0.3 / 2015-09-20

* Changed format of top-info payload to include version
* Added ability to turn off process table collection

0.0.2 / 2015-08-25

* Removed proof-of-life datapoint's plugin instance and changed name to host-uptime
* Made metadata plugic work from cmdline
* Added linux_version and collectd_version to meta-data
* Added Top Data sent

0.0.1 / 2015-08-18

* Send notifications when configured to
* Collect cpu, system and ec2 information and emit as notifications
* Emit single metric for proof of life

