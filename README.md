# PyTapo

Python library for communication with Tapo Cameras. 

[![Python version](https://img.shields.io/badge/python-3.6%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](https://opensource.org/licenses/MIT)
[![Tests](https://github.com/JurajNyiri/pytapo/workflows/Tests/badge.svg)](https://github.com/JurajNyiri/pytapo/actions)

## Installation:

```sh
python3 -m pip install pytapo
```

## Usage examples:

### Initiating the library:

```python
from pytapo import Tapo

user = "" # user you set in Advanced Settings -> Camera Account
password = "" # password you set in Advanced Settings -> Camera Account
host = "" # ip of the camera, example: 192.168.1.52

tapo = Tapo(host, user, password)

print(tapo.getBasicInfo())
```

## Authentication

Depending on your camera model and firmware version, the authentication method varies.

Normally you should be able to authenticate using the "camera account" created via the Tapo App (Settings > Advanced settings > Camera account).

In case of a similar stack trace:

```python
Traceback (most recent call last):
  File "/home/user/Projects/pytapo/pytapo/__init__.py", line 41, in __init__
    self.basicInfo = self.getBasicInfo()
  File "/home/user/Projects/pytapo/pytapo/__init__.py", line 232, in getBasicInfo
    return self.performRequest(
  File "/home/user/Projects/pytapo/pytapo/__init__.py", line 95, in performRequest
    self.ensureAuthenticated()
  File "/home/user/Projects/pytapo/pytapo/__init__.py", line 61, in ensureAuthenticated
    return self.refreshStok()
  File "/home/user/Projects/pytapo/pytapo/__init__.py", line 80, in refreshStok
    raise Exception("Invalid authentication data")
Exception: Invalid authentication data
```

Attempt to authenticate using `admin` as `user` and your TP-Link cloud account password as `password`.

## Downloading Recordings

Integration supports downloading recordings saved on camera's SD card. 

See the [example script](https://github.com/JurajNyiri/pytapo/blob/main/experiments/DownloadRecordings.py). 

Make sure to have the following environment variables set:

- `HOST`: IP Address of your camera
- `PASSWORD_CLOUD`: Tapo cloud account password. Required to access the recordings. Everything is still local.
- `OUTPUT`: Directory where you wish to save all the recordings.
- `DATE`: Date for which to download recordings in the format YYYYMMDD, for example, 20230221.

FFmpeg must also be installed as it is used for converting the streams to watchable files.

## Contributions:

We welcome contributions to Pytapo. Please note the following guidelines:

- Ensure you have 100% unit test coverage for any new changes.
- By creating a PR, you acknowledge that you are not breaking any TOS, law, and/or you have permission to provide and share the code changes.
- The owner of this repository is not legally responsible for any PRs or code changes to this project created by third parties.
- Tests are run on push and linters are run on every commit.

Please refer to the [test instructions](#test-instructions) for more details.

### Test Instructions

Set the following environment variables:

- `PYTAPO_USER` - user

 you set in Advanced Settings -> Camera Account
- `PYTAPO_PASSWORD` - password you set in Advanced Settings -> Camera Account
- `PYTAPO_IP` - ip of the camera, example: 192.168.1.52

Install `pre-commit` and `tox` from pip.

Run `pre-commit install` and `pre-commit install -t pre-push`.

Then run `tox` to run all the tests.

Note: While tests are running, your camera may perform all actions supported by this library, including, but not limited to, move, change privacy mode, and reboot. Rest assured that the camera does not format the SD card during tests. After the tests are done, your camera should be in the initial state.

## Credits

- [Dale Pavey](https://research.nccgroup.com/2020/07/31/lights-camera-hacked-an-insight-into-the-world-of-popular-ip-cameras/) from NCC Group for the initial research on the Tapo C200
- [likaci](https://github.com/likaci) and [his github repository](https://github.com/likaci/mercury-ipc-control) for the research on the Mercury camera on which Tapo is based
- [Tim Zhang](https://github.com/ttimasdf) for additional research for Mercury camera on [his github repository](https://github.com/ttimasdf/mercury-ipc-control)
- [Gábor Szabados](https://github.com/GSzabados) for doing research and gathering all the information above in [Home Assistant Community forum](https://community.home-assistant.io/t/use-pan-tilt-function-for-tp-link-tapo-c200-from-home-assistant/170143/18)
- [Davide Depau](https://github.com/Depau) for additional [research](https://md.depau.eu/s/r1Ys_oWoP) of the cameras and work on pytapo library
- [Alex X](https://github.com/AlexxIT) for his incredible work on go2rtc library, and its code for Tapo stream communication which was rewritten to python in order to implement stream-related features of this library

## Disclaimer

Pytapo is an unofficial module for achieving interoperability with Tapo cameras.

The author is in no way affiliated with Tp-Link or Tapo.

All the API requests used within the library are publicly available and published on the internet (examples linked above). This module is purely a wrapper around those HTTPS requests.

The author does not guarantee functionality of this library and is not responsible for any damage.

All product names, trademarks and registered trademarks in this repository, are the property of their respective owners.
