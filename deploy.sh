#!/bin/bash
setup_script="setup.py"
version=$(awk -F'"' '/version=/{print $2}' "$setup_script")
echo "Setting $version in version.py..."
echo "PYTAPO_VERSION = '$version'" > pytapo/version.py
rm -rf dist/*
python3 setup.py sdist bdist_wheel
python3 -m twine upload --repository pytapo dist/*