#!/bin/bash
set -e  # Exit the script if any command fails

# Specify the directory to be cleaned
DIST_DIRECTORY="../dist/*"

# Move to the directory containing the script
cd "$(dirname "$0")"

# Remove all files in the 'dist' directory
echo "Cleaning the distribution directory..."
rm -rf $DIST_DIRECTORY

# Make sure the cleanup was successful
if [[ $? -ne 0 ]]
then
  echo "Failed to clean the distribution directory."
  exit 1
fi
echo "Cleaned the distribution directory."

# Move back to the top level directory
cd ..

# Create the source distribution and wheel
echo "Creating the source distribution and wheel..."
python3 setup.py sdist bdist_wheel

# Make sure the distribution and wheel were created successfully
if [[ $? -ne 0 ]]
then
  echo "Failed to create the source distribution and wheel."
  exit 1
fi
echo "Created the source distribution and wheel."

# Upload the distribution to PyPi using twine
echo "Uploading the distribution to PyPi..."
python3 -m twine upload $DIST_DIRECTORY

# Make sure the upload was successful
if [[ $? -ne 0 ]]
then
  echo "Failed to upload the distribution to PyPi."
  exit 1
fi
echo "Uploaded the distribution to PyPi."

echo "Deployment completed successfully!"
