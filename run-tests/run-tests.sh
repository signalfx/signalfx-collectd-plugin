#! /bin/bash

SCRIPT_DIR=$(cd $(dirname $0) && pwd)

tempfolder=$(mktemp -d ${SCRIPT_DIR}/0.XXXXXX)
trap "rm -rf $tempfolder; docker stop signalfx-collectd-plugin-test; docker rm signalfx-collectd-plugin-test;" EXIT

# Copy the rest of the repo into tempfolder
cp $SCRIPT_DIR/../* $tempfolder
cp -r $SCRIPT_DIR/../src $tempfolder

# Copy the dockerfile to the tempfolder
cp $SCRIPT_DIR/Dockerfile $tempfolder

docker build -t signalfx-collectd-plugin-test $tempfolder

docker run --name signalfx-collectd-plugin-test -ti \
    -v $SCRIPT_DIR/../:/plugin signalfx-collectd-plugin-test /plugin/run-tests/cmdseq.sh
