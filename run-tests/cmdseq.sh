#! /bin/sh

pip install nose
pip install -r /plugin/requirements.txt
cd /plugin
echo "
Running tests...
"
for x in src/*.py; do python $x once; done

echo "
Running flake8...
"
python -m flake8 src/collectd_dogstatsd.py src/dummy_collectd.py src/test_dogstatsd.py src/signalfx_metadata.py
