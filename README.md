# PyTapo

PyTapo is a Python library that provides an interface for communicating with Tapo Cameras.

![Python version](https://img.shields.io/badge/python-3.6%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://github.com/JurajNyiri/pytapo/workflows/Tests/badge.svg)

## Getting Started:

### Installation:

Install the library using pip:

```sh
python3 -m pip install pytapo
```

### Usage:

First, initialize the PyTapo object with the host, username, and password:

```python
from pytapo import Tapo

user = "" # Username set in Advanced Settings -> Camera Account
password = "" # Password set in Advanced Settings -> Camera Account
host = "" # IP of the camera (e.g., 192.168.1.52)

tapo = Tapo(host, user, password)

print(tapo.getBasicInfo())
```

## Authentication:

Depending on your camera model and firmware, the authentication method may vary. Typically, you should authenticate using the "camera account" created via the Tapo App (Settings > Advanced settings > Camera account).

If you encounter an "Invalid authentication data" error, try authenticating using `admin` as `user` and your TP-Link cloud account password as `password`.

## Downloading Recordings:

PyTapo supports downloading recordings saved on the camera's SD card. Refer to the [example script](https://github.com/JurajNyiri/pytapo/blob/main/experiments/DownloadRecordings.py) for guidance. Ensure the following environment variables are set:

- `HOST`: IP Address of your camera
- `PASSWORD_CLOUD`: Tapo cloud account password (required for local access to recordings)
- `OUTPUT`: Directory for saving the recordings
- `DATE`: Date to download recordings (format YYYYMMDD, e.g., 20230221)

Please note, FFmpeg must be installed to convert streams to watchable files.

## Contributing:

Contributions to PyTapo are welcome. Please follow these guidelines:

- Ensure 100% unit test coverage for new changes.
- By creating a PR, you affirm that you are not violating any Terms of Service, law, and that you have permission to share the code changes.
- The repository owner is not legally responsible for PRs or code changes made by third parties.
- Tests are run on push and linters are run on every commit.

Refer to the [test instructions](#test-instructions) for more details.

### Test Instructions:

Set the following environment variables:

- `PYTAPO_USER`: Username set in Advanced Settings -> Camera Account
- `PYTAPO_PASSWORD`: Password set in Advanced Settings -> Camera Account
- `PYTAPO_IP`: IP of the camera (e.g., 192.168.1.52)

Install `pre-commit` and `tox` from pip. Then, run `pre-commit install` and `pre-commit install -t pre-push`, followed by `tox` to run all the tests. 

**Note**: While tests are running, your camera may perform all actions supported by this library. The SD card will not be formatted during tests, and the camera will return to its initial state afterward.

## Credits:

A host of contributors and researchers made PyTapo possible, including:

- [Dale Pavey](https://research.nccgroup.com/2020/07/31/lights-camera-hacked-an-insight-into-the-world-of-popular-ip-cameras/) from NCC Group
- [likaci](https://github.com/likaci) and his [github