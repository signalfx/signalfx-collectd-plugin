# Change Log

All notable changes to this project will be documented in this file.
Placeholder changes in the oldest release exist only to document which
subsections are relevant.
This project adheres to [Semantic Versioning](http://semver.org/).

## [0.0.8] - 2015-10-02
- wait one interval before sending notifications
- url error parsing more resilient
- add back in logical cpus
- better linux version checking

## [0.0.7] - 2015-09-29
- Remove dependence on requests

## [0.0.6] - 2015-09-27
- Add interfaces notifcation
- Remove logical cpus
- prefix with host_
- support /etc/os-release for linux_version
- Send LargeNotifs if message too large for collectd

## [0.0.5] - 2015-09-25
- Use host from collectd for Top Info notification
- Add mem_total for physical memory in kb

## [0.0.4] - 2015-09-20
- Top on amazon linux and better error handling

## [0.0.3] - 2015-09-20
- Changed format of top-info payload to include version
- Added ability to turn off process table collection

## [0.0.2] - 2015-08-25
- Removed proof-of-life datapoint's plugin instance and changed name to host-uptime
- Made metadata plugic work from cmdline
- Added linux_version and collectd_version to meta-data
- Added Top Data sent

## [0.0.1] - 2015-08-18

### Initial Release

- Send notifications when configured to
- Collect cpu, system and ec2 information and emit as notifications
- Emit single metric for proof of life

