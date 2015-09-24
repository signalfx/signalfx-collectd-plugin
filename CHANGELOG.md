# Change Log

All notable changes to this project will be documented in this file.
Placeholder changes in the oldest release exist only to document which
subsections are relevant.
This project adheres to [Semantic Versioning](http://semver.org/).

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

