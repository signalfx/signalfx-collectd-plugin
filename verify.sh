#!/bin/bash
set -x
set -e

if [ -z "$CIRCLE_TEST_REPORTS" ]; then
	export CIRCLE_TEST_REPORTS=/tmp
fi
mkdir -p "$CIRCLE_TEST_REPORTS/nosetests/"

nosetests -v --nologcapture -s --process-timeout 1s  --with-xunit --xunit-file="$CIRCLE_TEST_REPORTS/nosetests/junit.xml"

flake8 src/collectd_dogstatsd.py src/dummy_collectd.py src/test_dogstatsd.py src/signalfx_metadata.py

pylint src/test_dogstatsd.py src/dummy_collectd.py src/collectd_dogstatsd.py -r n

[ `grep "^VERSION =" src/signalfx_metadata.py | awk '{print $3}'` = \"`head -1 CHANGELOG.md | awk '{print $1}'`\" ]

for x in src/*.py; do python $x once; done
