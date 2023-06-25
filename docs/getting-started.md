## Installation

Getting started with PyTapo is easy. Install the package using pip:

```sh
python3 -m pip install pytapo
```

## Getting Started

Once installed, you can initiate the PyTapo object with the host, user, and password of your Tapo camera:

```python
from pytapo import Tapo

user = "" # Username set in Advanced Settings -> Camera Account
password = "" # Password set in Advanced Settings -> Camera Account
host = "" # IP of the camera (e.g., 192.168.1.52)

tapo = Tapo(host, user, password)

print(tapo.getBasicInfo())
```