#! /bin/sh

pip install nose
pip install -r /plugin/requirements.txt
cd /plugin
for x in src/*.py; do python $x once; done
