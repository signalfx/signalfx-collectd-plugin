Deprecation notice
==============================

Use of this plugin is deprecated.  To integrate collectd and SignalFx, please follow the instructions at https://support.signalfx.com/hc/en-us/articles/201094025-Use-collectd.  The short version is to add this to your collectd config:

```
LoadPlugin write_http
<Plugin "write_http">
 <URL "https://ingest.signalfx.com/v1/collectd">
 User "auth"
 Password "<<<<<<INSERT_TOKEN_HERE>>>>>>"
 Format "JSON"
 </URL>
</Plugin>
