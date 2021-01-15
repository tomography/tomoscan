"""Software for tomography scanning with EPICS at APS beamline 13-BM-D

   Classes
   -------
   TomoScan13BM
     Derived class for tomography scanning with EPICS at APS beamline 13-BM-D
     
"""
import time
import math
import os
from tomoscan_pso import TomoScanPSO
from tomoscan import log

class TomoScan13BM(TomoScanPSO):
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
