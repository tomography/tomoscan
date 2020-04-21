from epics import PV
from tomoscan import tomoscan

class tomoscan_13bm(tomoscan):

    def __init__(self, autoSettingsFile, macros=[]):
        tomoscan.__init__(self, autoSettingsFile, macros)
        
        prefix = self.pvPrefixes['MCS']
        if (prefix != None):
            self.controlPVs['MCSEraseStart']      = PV(prefix + 'EraseStart')
            self.controlPVs['MCSStopAll']         = PV(prefix + 'StopAll')
            self.controlPVs['MCSPrescale']        = PV(prefix + 'Prescale')
            self.controlPVs['MCSDwell']           = PV(prefix + 'Dwell')
            self.controlPVs['MCSLNEOutputWidth']  = PV(prefix + 'LNEOutputWidth')
            self.controlPVs['MCSChannelAdvance']  = PV(prefix + 'ChannelAdvance')
            self.controlPVs['MCSMaxChannels']     = PV(prefix + 'MaxChannels')
            self.controlPVs['MCSNuseAll']         = PV(prefix + 'NuseAll')
        self.epicsPVs = {**self.configPVs, **self.controlPVs}

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
            epicsPVs['CamImageMode'].put('Continuous')
            epicsPVs['CamTriggerMode'].put('Off')
            epicsPVs['CamExposureMode'].put('Timed')
        else: # set camera to external triggering
            epicsPVs['CamImageMode'].put('Multiple')
            epicsPVs['CamNumImages'].put(numImages)
            epicsPVs['CamTriggerMode'].put('On')
            epicsPVs['CamExposureMode'].put('Timed')
            epicsPVs['CamTriggerOverlap'].put('Readout')
            # Set number of MCS channels, NumImages, and NumCapture
            epicsPVs['MCSStopAll'].put(1)
            epicsPVs['MCSNuseAll'].put(numImages)
            epicsPVs['HdfNumCapture'].put(numImages)
  
        if (triggerMode == 'MCSExternal'):
            # Put MCS in external trigger mode
            epicsPVs['MCSStopAll'].put(1)
            epicsPVs['MCSChannelAdvance'].put('External')
  
  if (triggerMode eq 'MCSInternal') then begin
    t = caput(self.epics_pvs.sis_mcs+'StopAll', 1)
    ; Put MCS in internal trigger mode
    t = caput(self.epics_pvs.sis_mcs+'ChannelAdvance', 'Internal')
    ; Set MCS dwell time to time per angle
    t = caput(self.epics_pvs.sis_mcs+'Dwell', self->computeFrameTime())
  endif
  
end
