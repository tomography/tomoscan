from epics import PV
from tomoscan import tomoscan

class tomoscan_13bm(tomoscan):

    def __init__(self, autoSettingsFile, macros=[]):
        tomoscan.__init__(self, autoSettingsFile, macros)
        

    def configureCamera(self):
        a=0
    
    def collectDarkFields(self):
        a=0

    def collectFlatFields(self):
        a=0
      
    def collectNormalFields(self):
        a=0


    def setTriggerMode(self, triggerMode, numImages):
        if (triggerMode == 'FreeRun'):
            self.epicsPVs['CamImageMode'].put('Continuous', wait=True)
            self.epicsPVs['CamTriggerMode'].put('Off', wait=True)
            self.epicsPVs['CamExposureMode'].put('Timed', wait=True)
        else: # set camera to external triggering
            self.epicsPVs['CamImageMode'].put('Multiple', wait=True)
            self.epicsPVs['CamNumImages'].put(numImages, wait=True)
            self.epicsPVs['CamTriggerMode'].put('On', wait=True)
            self.epicsPVs['CamExposureMode'].put('Timed', wait=True)
            self.epicsPVs['CamTriggerOverlap'].put('ReadOut', wait=True)
            # Set number of MCS channels, NumImages, and NumCapture
            self.epicsPVs['MCSStopAll'].put(1, wait=True)
            self.epicsPVs['MCSNuseAll'].put(numImages, wait=True)
            self.epicsPVs['HdfNumCapture'].put(numImages, wait=True)
  
        if (triggerMode == 'MCSExternal'):
            # Put MCS in external trigger mode
            self.epicsPVs['MCSChannelAdvance'].put('External', wait=True)
  
        if (triggerMode == 'MCSInternal'):
            self.epicsPVs['MCSChannelAdvance'].put('Internal', wait=True)
            time = self.computeFrameTime()
            self.epicsPVs['MCSDwell'].put(time, wait=True)
