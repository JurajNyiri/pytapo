#
# Author: Juraj Nyiri
#

import requests
import hashlib
import json
import urllib3
from .const import ERROR_CODES, DEVICES_WITH_NO_PRESETS
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Tapo:
    def __init__(self, host, user, password):
        self.host = host
        self.user = user
        self.password = password
        self.stok = False
        self.headers = {
            'Host': self.host,
            'Referer': 'https://'+self.host+':443',
            'Accept': 'application/json',
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'Tapo CameraClient Android',
            'Connection': 'close',
            'requestByApp': 'true',
            'Content-Type': 'application/json; charset=UTF-8'
        }
        self.hashedPassword = hashlib.md5(password.encode('utf8')).hexdigest().upper()
        self.basicInfo = self.getBasicInfo()
        if(self.basicInfo['device_info']['basic_info']['device_model'] in DEVICES_WITH_NO_PRESETS):
            self.presets = {}
        else:
            self.presets = self.getPresets()

    def getHostURL(self):
        return 'https://'+self.host+':443'+'/stok='+self.stok+'/ds'

    def ensureAuthenticated(self):
        if(not self.stok):
            return self.refreshStok()
        return True

    def refreshStok(self):
        url = 'https://'+self.host+':443'
        data = {
            "method": "login",
            "params": {
                "hashed": True,
                "password": self.hashedPassword,
                "username": self.user
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            self.stok = json.loads(res.text)['result']['stok']
            return self.stok
        raise Exception("Invalid authentication data.")

    def responseIsOK(self, res):
        data = json.loads(res.text)
        return (res and data and data['error_code'] == 0)
    
    def getModuleSpec(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "function": {
                "name": ['module_spec']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.getModuleSpec(True)

    def getAudioSpec(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "audio_capability": {
                "name": ['device_speaker', 'device_microphone']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.getAudioSpec(True)

    def getVhttpd(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "cet": {
                "name": ['vhttpd']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.getVhttpd(True)

    def getBasicInfo(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "device_info": {
                "name": ['basic_info']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.getBasicInfo(True)

    def getTime(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "system": {
                "name": ['clock_status']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.getTime(True)

    def getMotorCapability(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "motor": {
                "name": ['capability']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.getMotorCapability(True)

    def setPrivacyMode(self, enabled, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()

        data = {
            "method": "set",
            "lens_mask": {
                "lens_mask_info": {
                    "enabled": "on" if enabled else "off"
                }
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.setPrivacyMode(enabled, True)

    def setAlarm(self, enabled, soundEnabled=True, lightEnabled=True, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        alarm_mode = []

        if(soundEnabled):
            alarm_mode.append("sound")
        if(lightEnabled):
            alarm_mode.append("light")

        data = {
            "method": "set",
            "msg_alarm": {
                "chn1_msg_alarm_info": {
                    "alarm_type":"0",
                    "enabled": "on" if enabled else "off",
                    "light_type":"0",
                    "alarm_mode": alarm_mode
                }
            }
        }
            
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.setAlarm(enabled, soundEnabled, lightEnabled, True)

    def moveMotor(self, x, y, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        
        data = { 
            "method": "do",
            "motor": {
                "move": {
                    "x_coord":str(x),
                    "y_coord":str(y)
                }
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.moveMotor(x, y, True)

    
    def format(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "do",
            "harddisk_manage": {
                "format_hd": "1"
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.format(True)

    def setLEDEnabled(self, enabled, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "set",
            "led": {
                "config": {
                    "enabled": "on" if enabled else "off"
                }
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.setLEDEnabled(enabled, True)

    def setMotionDetection(self, enabled, sensitivity=False, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "set",
            "motion_detection": {
                "motion_det": {
                    "enabled": "on" if enabled else "off"
                }
            }
        }
        if(sensitivity):
            if(sensitivity == "high"):
                data['motion_detection']['motion_det']['digital_sensitivity'] = "80"
            elif(sensitivity == "normal"):
                data['motion_detection']['motion_det']['digital_sensitivity'] = "50"
            elif(sensitivity == "low"):
                data['motion_detection']['motion_det']['digital_sensitivity'] = "20"
            else:
                raise Exception("Invalid sensitivity, can be low, normal or high.")

        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.setMotionDetection(enabled, sensitivity, True)

    def setAutoTrackTarget(self, enabled, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "set",
            "target_track": {
                "target_track_info": {
                    "enabled": "on" if enabled else "off"
                }
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.setAutoTrackTarget(enabled, True)

    def reboot(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "do",
            "system": {
                "reboot": "null"
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.reboot(True)

    def getPresets(self, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "preset": {
                "name": ["preset"]
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            self.presets = {}
            for key, id in enumerate(data['preset']['preset']['id']):
                self.presets[id] = data['preset']['preset']['name'][key]
            return self.presets
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.getPresets(True)
    
    def savePreset(self, name, raiseException = False):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "do",
            "preset": {
                "set_preset": {
                    "name": str(name),
                    "save_ptz": "1"
                }
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            self.getPresets()
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.savePreset(name, True)

    def deletePreset(self, presetID, raiseException = False):
        if(not str(presetID) in self.presets):
            raise Exception("Preset " + str(presetID) + " is not set in the app.")
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "do",
            "preset": {
                "remove_preset": {
                    "id": [presetID]
                }
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            self.getPresets()
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.deletePreset(presetID, True)

    def setPreset(self, presetID, raiseException = False):
        if(not str(presetID) in self.presets):
            raise Exception("Preset " + str(presetID) + " is not set in the app.")
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "do",
            "preset": {
                "goto_preset": {
                    "id": str(presetID)
                }
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            return True
        else:
            if(raiseException):
                raise Exception("Error: "+self.getErrorMessage(data['error_code'])+" Response:" + json.dumps(data))
            else:
                self.refreshStok()
                return self.setPreset(presetID, True)
    
    def getErrorMessage(self, errorCode):
        if(str(errorCode) in ERROR_CODES):
            return str(ERROR_CODES[str(errorCode)])
        else:
            return str(errorCode)