## Installation

You can install PyTapo via pip, Python's package installer:

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

## Camera Status and Basic Configuration

```python
basic_info = camera.getBasicInfo()              # Retrieve basic info about the camera
status = camera.getPrivacyMode()                # Retrieve privacy mode status
camera.setPrivacyMode(True)                     # Enable privacy mode
camera.setPrivacyMode(False)                    # Disable privacy mode
camera.setLED()                                 # Set the status of LED
LED_status = camera.getLED()                    # Get the status of LED
```

## Camera Settings

```python
camera.setDayNightMode()                        # Set Day/Night mode
day_night_mode = camera.getDayNightMode()       # Get Day/Night mode
camera.setNightVisionModeConfig()               # Set night vision mode configuration
night_vision_mode_config = camera.getNightVisionModeConfig()  # Get night vision mode configuration
camera.setLensDistortionCorrection()            # Set lens distortion correction
lens_correction = camera.getLensDistortionCorrection()  # Get lens distortion correction
camera.setLightFrequencyMode()                  # Set light frequency mode
light_frequency_mode = camera.getLightFrequencyMode()  # Get light frequency mode
```

## SD Card Access

```python
camera.format()                                 # Format the SD card
recordings = camera.getRecordings()             # Get recordings
recordings_list = camera.getRecordingsList()    # Get recordings list
```

## Motion Detection

```python
camera.setMotionDetection(True)                 # Enable motion detection
camera.setMotionDetection(False)                # Disable motion detection
motion_settings = camera.getMotionDetection()   # Get the current motion detection settings
```

## Video and Image Handling

```python
stream_url = camera.getStreamURL()              # Get the live stream URL
common_image = camera.getCommonImage()          # Capture a common image
camera.getImageFlipVertical()                   # Get image flip vertical status
camera.setImageFlipVertical()                   # Set image flip vertical
```

## Alarm and Detection Features

```python
alarm_config = camera.getAlarmConfig()          # Get alarm configuration
camera.setAlarm()                               # Set alarm
camera.startManualAlarm()                       # Start a manual alarm
camera.stopManualAlarm()                        # Stop a manual alarm
camera.setBabyCryDetection()                    # Set baby cry detection
baby_cry_detection = camera.getBabyCryDetection()   # Get baby cry detection
camera.setBarkDetection()                       # Set bark detection
bark_detection = camera.getBarkDetection()       # Get bark detection
```

## Motor Control

```python
camera.moveMotor(10, 20)                        # Move the motor to a specific coordinate
camera.moveMotorClockWise()                     # Move the motor clockwise
camera.moveMotorCounterClockWise()              # Move the motor counter-clockwise
camera.moveMotorHorizontal()                    # Move the motor horizontally
camera.moveMotorStep()                          # Move the motor a specific step
camera.moveMotorVertical()                      # Move the motor vertically
camera.calibrateMotor()                         # Calibrate the motor
motor_capability = camera.getMotorCapability()  # Get the motor capability
```