#
# Author: Juraj Nyiri
#

import requests
import hashlib
import json
import urllib3
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
    
    def getModuleSpec(self):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "function": {
                "name": ['module_spec']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            self.refreshStok()
            return self.getModuleSpec()

    def getAudioSpec(self):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "audio_capability": {
                "name": ['device_speaker', 'device_microphone']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            self.refreshStok()
            return self.getAudioSpec()

    def getVhttpd(self):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "cet": {
                "name": ['vhttpd']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            self.refreshStok()
            return self.getVhttpd()

    def getBasicInfo(self):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "device_info": {
                "name": ['basic_info']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            self.refreshStok()
            return self.getBasicInfo()

    def getTime(self):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "system": {
                "name": ['clock_status']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            self.refreshStok()
            return self.getTime()

    def getMotorCapability(self):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "get",
            "motor": {
                "name": ['capability']
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            return json.loads(res.text)
        else:
            self.refreshStok()
            return self.getMotorCapability()

    def setPrivacyMode(self, enabled):
        self.ensureAuthenticated()
        url = self.getHostURL()

        data = {
            "method": "multipleRequest",
            "params": {
                "requests": [{
                    "method": "setLensMaskConfig",
                    "params": {
                        "lens_mask": {
                            "lens_mask_info": {
                                "enabled": "on" if enabled else "off"
                            }
                        }
                    }
                }]
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            data = json.loads(res.text)['result']['responses'][0]
            if(data['error_code'] != 0):
                return False
            else:
                return True
        else:
            self.refreshStok()
            return self.setPrivacyMode(enabled)

    def setAlarm(self, enabled, soundEnabled=True, lightEnabled=True):
        self.ensureAuthenticated()
        url = self.getHostURL()
        alarm_mode = []

        if(soundEnabled):
            alarm_mode.append("sound")
        if(lightEnabled):
            alarm_mode.append("light")

        data = {
            "method": "multipleRequest",
            "params": {
                "requests": [{
                    "method": "setAlertConfig",
                    "params": {
                        "msg_alarm": {
                            "chn1_msg_alarm_info": {
                                "alarm_type":"0",
                                "enabled": "on" if enabled else "off",
                                "light_type":"0",
                                "alarm_mode": alarm_mode
                            }
                        }
                    }
                }]
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            data = json.loads(res.text)['result']['responses'][0]
            if(data['error_code'] != 0):
                return False
            else:
                return True
        else:
            self.refreshStok()
            return self.setAlarm(enabled, soundEnabled, lightEnabled)

    def moveMotor(self, x, y):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "multipleRequest",
            "params": {
                "requests": [{
                    "method": "motorMove",
                    "params": {
                        "motor": {
                            "move": {
                                "x_coord":str(x),
                                "y_coord":str(y)
                            }
                        }
                    }
                }]
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            data = json.loads(res.text)['result']['responses'][0]
            if(data['error_code'] != 0):
                # motor cannot move further, usually error -64304
                return False
            else:
                return True
        else:
            self.refreshStok()
            return self.moveMotor(x, y)

    
    def format(self):
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {
            "method": "multipleRequest",
            "params": {
                "requests": [{
                    "method": "formatSdCard",
                    "params": {
                        "harddisk_manage": {
                            "format_hd": "1"
                        }
                    }
                }]
            }
        }
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        if(self.responseIsOK(res)):
            data = json.loads(res.text)['result']['responses'][0]
            if(data['error_code'] != 0):
                return False
            else:
                return True
        else:
            self.refreshStok()
            return self.format()

    def setLEDEnabled(self, enabled):
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
            self.refreshStok()
            return self.setLEDEnabled(enabled)

    def setMotionDetection(self, enabled, sensitivity=False):
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
            self.refreshStok()
            return self.setMotionDetection(enabled, sensitivity)

    def setAutoTrackTarget(self, enabled):
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
            self.refreshStok()
            return self.setAutoTrackTarget(enabled)

    def reboot(self):
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
            self.refreshStok()
            return self.reboot()

    def getPresets(self):
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
            self.presets = data['preset']['preset']['id']
            return self.presets
        else:
            self.refreshStok()
            return self.getPresets()
    
    def savePreset(self, name):
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
            self.refreshStok()
            return self.savePreset(name)

    def deletePreset(self, presetID):
        raise Exception("Todo: deletePreset")
        if(not str(presetID) in self.presets):
            raise Exception("Preset " + str(presetID) + " is not set in the app.")
        self.ensureAuthenticated()
        url = self.getHostURL()
        data = {}
        res = requests.post(url, data = json.dumps(data), headers=self.headers, verify=False)
        data = json.loads(res.text)
        if(self.responseIsOK(res)):
            self.getPresets()
            return True
        else:
            self.refreshStok()
            self.getPresets()
            #return self.deletePreset(presetID)

    def setPreset(self, presetID):
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
        elif(data['error_code'] == -64302): # ID not found
            return False
        else:
            self.refreshStok()
            return self.setPreset(presetID)