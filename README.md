>ℹ️&nbsp;&nbsp;SignalFx was acquired by Splunk in October 2019. See [Splunk SignalFx](https://www.splunk.com/en_us/investor-relations/acquisitions/signalfx.html) for more information.

SignalFx Metadata Plugin
==============================

Provides metadata about host and will send collectd notifications to SignalFx
if configured to do so.

Example Config:

```
LoadPlugin python
TypesDB "/opt/signalfx-collectd-plugin/types.db.plugin"
<Plugin python>
  ModulePath "/opt/signalfx-collectd-plugin"
  LogTraces true
  Interactive false
  Import "signalfx_metadata"
  <Module signalfx_metadata>
    URL "https://ingest.signalfx.com/v1/collectd"
    Token "<<<<<<INSERT_TOKEN_HERE>>>>>>"
    Notifications true
    NotifyLevel "OKAY"
    Utilization true
    Interval 10
  </Module>
</Plugin>
```

For metadata:

* ProcessInfo: do we want to collect process information, true or false.
  Default is true.
* Notifications: do we want to emit notifications from the plugin true or
  false. Default is false. Note, the plugin will send it's own metadata as
  events in addition to this.
* URL: where to emit notifications via json to. The example url is the default.
  Supports multiple entries.
* Token: api token from signalfx to authenticate. No default. Required for
  metadata unless talking through proxy.  Supports multiple entries but
  cardinality must equal that of URLs.
* Interval: how often you want the sfx plugin to collect and send data.
  Default is 10.
* NotifyLevel: If you want to emit notifications beyond the ones generated by
  this plugin, set to the appropriate level. "OKAY" would mean all
  notifications are emitted.  "ERROR" would just be error.  "WARNING" would
  include "ERROR" and "WARNING".
* Utilization: would you like the plugin to send in utilization metrics?
  Default is true.
* PerCoreCPUUtil: would you like the plugin to send in utilization metrics for
  each processor?  Default is false
* Datapoints: would you like the plugin to send in metrics about max round
  trip time, plugin uptime and notification sending errors?  Default is true.
* ProcPath: specify an alternate `proc` path to parse for process information.
  Default is `/proc`.
* EtcPath: specify an alternate `etc` path to parse for os release information.
  Default is `/etc`.

For DogstatsD support:

* To enable reading of DogstatsD metrics, add a line similar to the following
  to your config inside the Module block  ```DogStatsDPort 8126```
