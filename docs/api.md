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
status = camera.get_status()
```

Change the camera's status, such as toggling the privacy mode:

```python
camera.set_privacy_mode(True)  # Enable privacy mode
camera.set_privacy_mode(False) # Disable privacy mode
```

### SD Card Access

Fetch a list of all files saved on the SD card:

```python
files = camera.get_sd_card_record_files()
```

Download a specific file from the SD card:

```python
camera.download_sd_card_record_file('recordfile.mp4', '/path/to/download/location/')
```

### Image Capture

Capture a live image from the camera and save the data:

```python
image_data = camera.get_live_image()

with open('image.jpg', 'wb') as file:
    file.write(image_data)
```

## Advanced Features

### Video Streaming

Stream live video feed from the camera:

```python
stream = camera.get_live_stream()

# `stream` can now be used with a video player or further processing
```

### Motion Detection

Adjust motion detection settings:

```python
# Enable motion detection
camera.set_motion_detection(True)

# Set detection sensitivity to high (1-10)
camera.set_detection_sensitivity(10)

# Get the current motion detection settings
motion_settings = camera.get_motion_detection()
```

### Network Settings

Retrieve the camera's network settings:

```python
network_settings = camera.get_network_settings()
```

Change the camera's network settings:

```python
camera.set_network_settings({
    'type': 'dynamic',  # dynamic, static, or pppoe
    'ipAddress': '192.168.0.100',
    'subnetMask': '255.255.255.0',
    'defaultGateway': '192.168.0.1',
    'primaryDNS': '192.168.0.1',
    'secondaryDNS': '8.8.8.8',
})
```

### Motor Control

Control the direction of the camera's motor:

```python
# Move the camera's motor to a specific coordinate
camera.move_motor(10, 20)

# Move the camera's motor a specific angle
camera.move_motor_step(90)

# Move the camera's motor clockwise
camera.move_motor_clockwise()

# Move the camera's motor counterclockwise
camera.move_motor_counterclockwise()

# Move the camera's motor vertically
camera.move_motor_vertical()

# Move the camera's motor horizontally
camera.move_motor_horizontal()

# Calibrate the camera's motor
camera.calibrate_motor()

# Get the capability of the camera's motor
capability = camera.get_motor_capability()
```

### Get Most Configuration

Fetch most of the camera configuration details:

```python
config = camera.get_most()
```

## Error Handling

PyTapo throws a `TapoException` for encountered errors. You can catch these exceptions and handle them accordingly:

```python
from pytapo import Tapo, TapoException

try:
    camera = Tapo('192.168.0.10', 'admin', 'wrongpassword')
except Tapo