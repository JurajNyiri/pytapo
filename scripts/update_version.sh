#!/bin/bash

new_version="0.1.2"  # Replace with the desired new version number

# Update pyproject.toml
awk -v new_version="$new_version" '/^version =/ {$NF = "\"" new_version "\""} 1' ../pyproject.toml > tmp && mv tmp ../pyproject.toml

# Update app/__version__.py
awk -v new_version="$new_version" '/^__version__ =/ {$NF = "\"" new_version "\""} 1' ../pytapo/__version__.py > tmp && mv tmp ../pytapo/__version__.py

echo "Version updated to $new_version"