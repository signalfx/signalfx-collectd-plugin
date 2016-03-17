0.0.18 / 2016-03-21
===================

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

