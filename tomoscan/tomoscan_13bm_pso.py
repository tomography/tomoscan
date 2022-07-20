"""Software for tomography scanning with EPICS at APS beamline 13-BM-D

   Classes
   -------
   TomoScan13BM
     Derived class for tomography scanning with EPICS at APS beamline 13-BM-D
     using the Aerotech A3200 and NDrive as the rotation stage and trigger source  
"""
import time
import math
import os
from tomoscan.tomoscan_pso import TomoScanPSO
from tomoscan import log

class TomoScan13BM_PSO(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 13-BM-D
       using the Aerotech A3200 and NDrive as the rotation stage and trigger source

    Parameters
    ----------
    pv_files : list of str
        List of files containing EPICS pvNames to be used.
    macros : dict
        Dictionary of macro definitions to be substituted when
        reading the pv_files
    """

    def __init__(self, pv_files, macros):
        super().__init__(pv_files, macros)

        # Set the detector running in FreeRun mode
        self.set_trigger_mode('FreeRun', 1)

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode of the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
            This is used to set the ``NumImages`` PV of the camera.
        """
        log.info('set trigger mode: %s', trigger_mode)
        # Stop acquisition if we are acquiring
        self.epics_pvs['CamAcquire'].put('Done', wait=True)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamAcquire'].put('Acquire')
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else: # set camera to external triggering
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            # There is a problem with the Grasshopper3 when switching to external trigger mode.
            # The first 3 images are bad, at least at long exposure times.
            # We take 3 dummy frames with Software trigger mode and don't save them to HDF5 file.
            self.epics_pvs['CamImageMode'].put('Single', wait=True)
            self.epics_pvs['CamTriggerSource'].put('Software', wait=True)
            exposure = self.epics_pvs['CamAcquireTimeRBV'].value
            self.epics_pvs['FPEnableCallbacks'].put('Disable', wait=True)
            for i in range(3):
                self.epics_pvs['CamAcquire'].put('Acquire')
                time.sleep(.1)
                self.epics_pvs['CamTriggerSoftware'].put(1, wait=True)
                self.wait_camera_done(exposure + 5)
            self.epics_pvs['FPEnableCallbacks'].put('Enable', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple', wait=True)
            self.epics_pvs['CamTriggerSource'].put('Line0', wait=True)
