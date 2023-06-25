## Installation

You can install PyTapo via pip, Python's package installer. Run the following command in your terminal:

```bash
pip install pytapo
```

To start using PyTapo in your Python script, import the `Tapo` class:

```python
from pytapo import Tapo
```

Create an instance of the `Tapo` class with your camera's IP address and your Tapo account credentials:

```python
camera = Tapo('192.168.0.10', 'admin', 'password')
```

## Core Features

### Camera Status

Retrieve the current status of the camera:

```python
status = camera.getStatus()
```

Change the camera's status, such as toggling the privacy mode:

```python
camera.setPrivacyMode(True)  # Enable privacy mode
camera.setPrivacyMode(False) # Disable privacy mode
```

### SD Card Access

Fetch a list of all files saved on the SD card:

```python
files = camera.getSDCardRecordFiles()
```

Download a specific file from the SD card:

```python
camera.downloadSDCardRecordFile('recordfile.mp4', '/path/to/download/location/')
```

### Image Capture

Capture a live image from the camera and save the data:

```python
image_data = camera.getLiveImage()

with open('image.jpg', 'wb') as file:
    file.write(image_data)
```

## Advanced Features

### Video Streaming

Stream live video feed from the camera:

```python
stream = camera.getLiveStream()

# `stream` can now be used with a video player or further processing
```

### Motion Detection

Adjust motion detection settings:

```python
# Enable motion detection
camera.setMotionDetection(True)

# Set detection sensitivity to high (1-10)
camera.setDetectionSensitivity(10)

# Get the current motion detection settings
motion_settings = camera.getMotionDetection()
```

### Network Settings

Retrieve the camera's network settings:

```python
network_settings = camera.getNetworkSettings()
```

Change the camera's network settings:

```python
camera.setNetworkSettings({
    'type': 'dynamic',  # dynamic, static, or pppoe
    'ipAddress': '192.168.0.100',
    'subnetMask': '255.255.255.0',
    'defaultGateway': '192.168.0.1',
    'primaryDNS': '192.168.0.1',
    'secondaryDNS': '8.8.8.8',
})
```

## Error Handling

PyTapo throws a `TapoException` for encountered errors. You can catch these exceptions and handle them accordingly:

```python
from pytapo import Tapo, TapoException

try:
    camera = Tapo('192.168.0.10', 'admin', 'wrongpassword')
except TapoException as e:
    print(f'Error: {e.message}')
```

## Camera Configuration

### Reboot the Camera

Reboot the Tapo camera:

```python
camera.reboot()
```

### Set Camera Resolution

Set the resolution of the Tapo camera:

```python
camera.setResolution('1080p')  # Set resolution to 1080p
camera.setResolution('720p')   # Set resolution to 720p
```

### Adjust Camera Rotation

Rotate the Tapo camera:

```python
camera.rotate(90)   # Rotate the camera by 90 degrees clockwise
camera.rotate(-90)  # Rotate the camera by 90 degrees counterclockwise
```