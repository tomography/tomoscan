from epics import PV
import json

class tomoscan:

    def __init__(self, autoSettingsFile, macros=[]):
        self.configPVs = {}
        self.controlPVs = {}
        self.pvPrefixes = {}
        if (autoSettingsFile != None):
            self.readAutoSettingsFile(autoSettingsFile, macros)

        prefix = self.pvPrefixes['Camera']
        if (prefix != None):
            camPrefix = prefix + 'cam1:'
            self.controlPVs['CamAcquire']         = PV(camPrefix + 'Acquire')
            self.controlPVs['CamImageMode']       = PV(camPrefix + 'ImageMode')
            self.controlPVs['CamTriggerMode']     = PV(camPrefix + 'TriggerMode')
            self.controlPVs['CamNumImages']       = PV(camPrefix + 'NumImages')
            self.controlPVs['CamAcquireTime']     = PV(camPrefix + 'AcquireTime')
            self.controlPVs['CamWaitForPlugins']  = PV(camPrefix + 'WaitForPlugins')
            hdfPrefix = prefix + 'HDF1:'
            self.controlPVs['HdfFileWriteMode']   = PV(hdfPrefix + 'FileWriteMode')
            self.controlPVs['HdfNumCapture']      = PV(hdfPrefix + 'NumCapture')
            self.controlPVs['HdfCapture']         = PV(hdfPrefix + 'Capture')
            self.controlPVs['HdfFilePath']        = PV(hdfPrefix + 'FilePath')
            self.controlPVs['HdfFileName']        = PV(hdfPrefix + 'FileName')
            self.controlPVs['HdfFullFileName']    = PV(hdfPrefix + 'FullFileName_RBV')
            
            # Set some initial PV values
            self.controlPVs['CamWaitForPlugins'].put('Yes')
            filePath = self.configPVs['FilePath'].char_value
            self.controlPVs['HdfFilePath'].put(filePath)
            fileName = self.configPVs['FileName'].char_value
            self.controlPVs['HdfFileName'].put(filePath)
             
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

