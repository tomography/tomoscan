from epics import PV
import json
import time

class tomoscan:

    def __init__(self, autoSettingsFile, macros=[]):
        self.configPVs = {}
        self.controlPVs = {}
        self.pvPrefixes = {}
        if (autoSettingsFile != None):
            self.readAutoSettingsFile(autoSettingsFile, macros)

        if (('Rotation' in self.controlPVs) == False):
            print("ERROR: RotationPVName must be present in autoSettingsFile")
            quit()
        if (('Camera' in self.pvPrefixes) == False):
            print("ERROR: CameraPVPrefix must be present in autoSettingsFile")
            quit()
        if (('FilePlugin' in self.pvPrefixes) == False):
            print("ERROR: FilePluginPVPrefix must be present in autoSettingsFile")
            quit()
                        
        rotationPVName = self.controlPVs['Rotation'].pvname
        self.controlPVs['RotationSpeed']      = PV(rotationPVName + '.VELO')
        self.controlPVs['RotationMaxSpeed']   = PV(rotationPVName + '.VMAX')
        self.controlPVs['RotationResolution'] = PV(rotationPVName + '.MRES')

        prefix = self.pvPrefixes['Camera']
        camPrefix = prefix + 'cam1:'
        self.controlPVs['CamManufacturer']    = PV(camPrefix + 'Manufacturer_RBV')
        self.controlPVs['CamModel']           = PV(camPrefix + 'Model_RBV')
        self.controlPVs['CamAcquire']         = PV(camPrefix + 'Acquire')
        self.controlPVs['CamAcquireBusy']     = PV(camPrefix + 'AcquireBusy')
        self.controlPVs['CamImageMode']       = PV(camPrefix + 'ImageMode')
        self.controlPVs['CamTriggerMode']     = PV(camPrefix + 'TriggerMode')
        self.controlPVs['CamNumImages']       = PV(camPrefix + 'NumImages')
        self.controlPVs['CamAcquireTime']     = PV(camPrefix + 'AcquireTime')
        self.controlPVs['CamAcquireTimeRBV']  = PV(camPrefix + 'AcquireTime_RBV')
        self.controlPVs['CamBinX']            = PV(camPrefix + 'BinX')
        self.controlPVs['CamBinY']            = PV(camPrefix + 'BinY')
        self.controlPVs['CamWaitForPlugins']  = PV(camPrefix + 'WaitForPlugins')
        
        # If this is a Point Grey camera then assume we are running ADSpinnaker
        # and create some PVs specific to that driver
        manufacturer = self.controlPVs['CamManufacturer'].char_value
        model = self.controlPVs['CamModel'].char_value
        if (manufacturer.find('Point Grey') != -1):
            self.controlPVs['CamExposureMode']   = PV(camPrefix + 'ExposureMode')
            self.controlPVs['CamTriggerOverlap'] = PV(camPrefix + 'TriggerOverlap')
            self.controlPVs['CamPixelFormat']    = PV(camPrefix + 'PixelFormat')
            if (model.find('Grasshopper3') != -1):
                self.controlPVs['CamVideoMode']  = PV(camPrefix + 'GC_VideoMode_RBV')

        # Set some initial PV values                
        self.controlPVs['CamWaitForPlugins'].put('Yes')
 
        prefix = self.pvPrefixes['FilePlugin']
        self.controlPVs['FPFileWriteMode']   = PV(prefix + 'FileWriteMode')
        self.controlPVs['FPNumCapture']      = PV(prefix + 'NumCapture')
        self.controlPVs['FPCapture']         = PV(prefix + 'Capture')
        self.controlPVs['FPFilePath']        = PV(prefix + 'FilePath')
        self.controlPVs['FPFileName']        = PV(prefix + 'FileName')
        self.controlPVs['FPFileNumber']      = PV(prefix + 'FileNumber')
        self.controlPVs['FPAutoIncrement']   = PV(prefix + 'AutoIncrement')
        self.controlPVs['FPFullFileName']    = PV(prefix + 'FullFileName_RBV')
        self.controlPVs['FPAutoSave']        = PV(prefix + 'AutoSave')
        self.controlPVs['FPEnableCallbacks'] = PV(prefix + 'EnableCallbacks')
        
        # Set some initial PV values
        filePath = self.configPVs['FilePath'].char_value
        self.controlPVs['FPFilePath'].put(filePath)
        fileName = self.configPVs['FileName'].char_value
        self.controlPVs['FPFileName'].put(fileName)
        self.controlPVs['FPAutoSave'].put('No')
        self.controlPVs['FPFileWriteMode'].put('Stream')
        self.controlPVs['FPEnableCallbacks'].put('Enable')

        if ('MCS' in self.pvPrefixes):             
            prefix = self.pvPrefixes['MCS']
            self.controlPVs['MCSEraseStart']      = PV(prefix + 'EraseStart')
            self.controlPVs['MCSStopAll']         = PV(prefix + 'StopAll')
            self.controlPVs['MCSPrescale']        = PV(prefix + 'Prescale')
            self.controlPVs['MCSDwell']           = PV(prefix + 'Dwell')
            self.controlPVs['MCSLNEOutputWidth']  = PV(prefix + 'LNEOutputWidth')
            self.controlPVs['MCSChannelAdvance']  = PV(prefix + 'ChannelAdvance')
            self.controlPVs['MCSMaxChannels']     = PV(prefix + 'MaxChannels')
            self.controlPVs['MCSNuseAll']         = PV(prefix + 'NuseAll')
 
        self.epicsPVs = {**self.configPVs, **self.controlPVs}

    def showPVs(self):
        print("configPVS:")
        for pv in self.configPVs:
            print(pv, ":", self.configPVs[pv].get(as_string=True))

        print("")
        print("controlPVS:")
        for pv in self.controlPVs:
            print(pv, ":", self.controlPVs[pv].get(as_string=True))

        print("")
        print("pvPrefixes:")
        for pv in self.pvPrefixes:
            print(pv, ":", self.pvPrefixes[pv])

    def readAutoSettingsFile(self, autoSettingsFile, macros):
        f = open(autoSettingsFile)
        lines = f.read()
        f.close()
        lines = lines.splitlines()
        for line in lines:
            pvname = line
            # Do macro substitution
            for key in macros:
                 pvname = pvname.replace(key, macros[key])
            dictentry = line
            for key in macros:
                 dictentry = dictentry.replace(key, "")
            pv = PV(pvname)
            self.configPVs[dictentry] = pv
            if (dictentry.find("PVName") != -1):
                pvname = pv.value
                de = dictentry.strip("PVName")
                self.controlPVs[de] = PV(pvname)
            if (dictentry.find("PVPrefix") != -1):
                pvprefix = pv.value
                de = dictentry.strip("PVPrefix")
                self.pvPrefixes[de] = pvprefix

    def moveSampleIn(self):
        axis = self.epicsPVs["FlatFieldAxis"].char_value
        print("moveSampleIn axis:", axis)
        if (axis == "X") or (axis == "Both"):
            position = self.epicsPVs["SampleInX"].value
            self.epicsPVs["SampleX"].put(position, wait=True)
            
        if (axis == "Y") or (axis == "Both"):
            position = self.epicsPVs["SampleInY"].value
            self.epicsPVs["SampleY"].put(position, wait=True)

    def moveSampleOut(self):
        axis = self.epicsPVs["FlatFieldAxis"].char_value
        print("moveSampleOut axis:", axis)
        if (axis == "X") or (axis == "Both"):
            position = self.epicsPVs["SampleOutX"].value
            self.epicsPVs["SampleX"].put(position, wait=True)
            
        if (axis == "Y") or (axis == "Both"):
            position = self.epicsPVs["SampleOutY"].value
            self.epicsPVs["SampleY"].put(position, wait=True)

    def saveConfiguration(self, fileName):
        d = {}
        for pv in self.configPVs:
            d[pv] = self.configPVs[pv].char_value
        f = open(fileName, "w")
        json.dump(d, f, indent=2)
        f.close()
    
    def loadConfiguration(self, fileName):
        f = open(fileName, "r")
        d = json.load(f)
        f.close()
        for pv in d:
            self.configPVs[pv].put(d[pv])

    def openShutter(self):
        if (self.epicsPVs['OpenShutter'] != None):
            value = self.epicsPVs['OpenShutterValue'].char_value
            self.epicsPVs['OpenShutter'].put(value, wait=True)

    def closeShutter(self):
        if (self.epicsPVs['OpenShutter'] != None):
            value = self.epicsPVs['OpenShutterValue'].char_value
            self.epicsPVs['OpenShutter'].put(value, wait=True)

    def flyScan(self):
        rotationStart = self.epicsPVs['RotationStart'].value
        rotationStep = self.epicsPVs['RotationStart'].value
        numAngles = self.epicsPVs['NumAngles'].value
        rotationStop = rotationStart + (numAngles * rotationStep)
        numDarkFields = self.epicsPVs['NumDarkFields'].value
        darkFieldMode = self.epicsPVs['DarkFieldMode'].value
     
        self.epicsPVs['Rotation'].put(rotationStart, wait=True)

        self.configureCamera()

        if (numDarkFields > 0) and ((darkFieldMode == 'Start') or (darkFieldMode == 'Both')):
            self.closeShutter()
            self.collectDarkFields(numDarkFields)
        
        self.openShutter()
    
        if (numFlatFields > 0) and ((flatFieldMode == 'Start') or (flatFieldMode == 'Both')):
            self.moveSampleOut()
            self.collectFlatFields(numFlatFields)
            
        self.moveSampleIn()
    
        collectNormalFields(numAngles)
        
        if (numFlatFields > 0) and ((flatFieldMode == 'End') or (flatFieldMode == 'Both')):
            self.moveSampleOut()
            self.collectFlatFields(numDarkFields)
            self.moveSampleIn()
    
        if (numDarkFields > 0) and ((darkFieldMode == 'End') or (darkFieldMode == 'Both')):
            self.closeShutter()
            self.collectDarkFields(numDarkFields)
            self.openShutter()

    def computeFrameTime(self):
        exposure = self.epicsPVs['ExposureTime'].value
        self.epicsPVs['CamAcquireTime'].put(exposure, wait=True)
        # The readout time of the camera depends on the model, and things like the PixelFormat, VideoMode, etc.
        # The measured times in ms with 100 microsecond exposure time and 1000 frames without dropping
        cameraModel = self.epicsPVs['CamModel'].get(as_string=True)
        pixelFormat = self.epicsPVs['CamPixelFormat'].get(as_string=True)
        if (cameraModel == 'Grasshopper3 GS3-U3-23S6M'): 
            videoMode   = self.epicsPVs['CamVideoMode'].get(as_string=True)
            readoutTimes = {'Mono8':        {'Mode0': 6.2, 'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 7.9},
                            'Mono12Packed': {'Mode0': 9.2, 'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 11.5},
                            'Mono16':       {'Mode0': 12.2,'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 12.2}}       
            readout = readoutTimes[pixelFormat][videoMode]/1000.
        
        if (readout == None):
            print('Unsupported combination of camera model, pixel format and video mode: ',
                  cameraModel, pixelFormat, videoMode)
            return 0

        # We need to use the actual exposure time that the camera is using, not the requested exposure time
        exposure = self.epicsPVs['CamAcquireTimeRBV'].value
        # Add 1 or 5 ms to exposure time for margin
        if (exposure > 2.3):
            time = exposure + .005 
        else:
            time = exposure + .001

        # If the time is less than the readout time then use the readout time
        if (time < readout):
            time = readout
        return time

    def waitCameraDone(self, timeout):
        startTime = time.time()
        while(True):
            if (self.epicsPVs['CamAcquireBusy'].value == 0):
                return True
            time.sleep(0.01)
            if (timeout > 0):
                currentTime = time.time()
                diffTime = currentTime - startTime
                if diffTime >= timeout:
                    print('ERROR: timeout waiting for camera to be done')
                    return False
