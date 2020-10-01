# PyTapo
Python library for communication with Tapo Cameras

## Install:

```
python3 -m pip install pytapo
```

## Usage examples:

### Initiate library:
```
from pytapo import Tapo

user = "" # user you set in Advanced Settings -> Camera Account
password = "" # password you set in Advanced Settings -> Camera Account
host = "" # ip of the camera, example: 192.168.1.52

tapo = Tapo(host, user, password)

print(tapo.getBasicInfo())
```