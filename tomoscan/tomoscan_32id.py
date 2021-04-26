"""Software for tomography scanning with EPICS at APS beamline 32-ID

   Classes
   -------
   TomoScan2BM
     Derived class for tomography scanning with EPICS at APS beamline 32-ID
"""
import time
import os
import h5py 
import sys
import traceback
import numpy as np

from tomoscan import data_management as dm
from tomoscan import TomoScanPSO
from tomoscan import log

EPSILON = .001

class TomoScan32ID(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 32-ID

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
        # self.set_trigger_mode('FreeRun', 1)
        # self.epics_pvs['CamAcquire'].put('Acquire') ###
        # self.wait_pv(self.epics_pvs['CamAcquire'], 1) ###

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Set standard file template on file writer
        self.epics_pvs['FPFileTemplate'].put("%s%s_%3.3d.h5", wait=True)

        # Disable over writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

        log.setup_custom_logger("./tomoscan.log")

    def move_crl_in(self):
        """Moves the crl in.
        """
        self.control_pvs['CRLRelaysY0'].put(1, wait=True, timeout=1)
        # self.control_pvs['CRLRelaysY1'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY2'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY3'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY4'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY5'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY6'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY7'].put(1, wait=True, timeout=1)

        self.epics_pvs['MoveCRLIn'].put('Done')

    def move_crl_out(self):
        """Moves the crl out.
        """
        self.control_pvs['CRLRelaysY0'].put(0, wait=True, timeout=1)
        # self.control_pvs['CRLRelaysY1'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY2'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY3'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY4'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY5'].put(0, wait=True, timeout=1)
        # self.control_pvs['CRLRelaysY6'].put(0, wait=True, timeout=1)
        # self.control_pvs['CRLRelaysY7'].put(0, wait=True, timeout=1)

        self.epics_pvs['MoveCRLOut'].put('Done')

    def move_diffuser_in(self):
        """Moves the diffuser in.
        """
        position = self.epics_pvs['DiffuserInX'].value
        self.epics_pvs['DiffuserX'].put(position, wait=True)

        self.epics_pvs['MoveDiffuserIn'].put('Done')

    def move_diffuser_out(self):
        """Moves the diffuser out.
        """
        position = self.epics_pvs['DiffuserOutX'].value
        self.epics_pvs['DiffuserX'].put(position, wait=True)

        self.epics_pvs['MoveDiffuserOut'].put('Done')

    def move_beamstop_in(self):
        """Moves the beamstop in.
        """
        position = self.epics_pvs['BeamstopInY'].value
        self.epics_pvs['BeamstopY'].put(position, wait=True)

        self.epics_pvs['MoveBeamstopIn'].put('Done')

    def move_beamstop_out(self):
        """Moves the beamstop out.
        """
        position = self.epics_pvs['BeamstopOutY'].value
        self.epics_pvs['BeamstopY'].put(position, wait=True)

        self.epics_pvs['MoveBeamstopOut'].put('Done')

    def move_pinhole_in(self):
        """Moves the pinhole in.
        """
        position = self.epics_pvs['PinholeInY'].value
        self.epics_pvs['PinholeY'].put(position, wait=True)

        self.epics_pvs['MovePinholeIn'].put('Done')

    def move_pinhole_out(self):
        """Moves the pinhole out.
        """
        position = self.epics_pvs['PinholeOutY'].value
        self.epics_pvs['PinholeY'].put(position, wait=True)

        self.epics_pvs['MovePinholeOut'].put('Done')

    def move_condenser_in(self):
        """Moves the condenser in.
        """
        position = self.epics_pvs['CondenserInY'].value
        self.epics_pvs['CondenserY'].put(position, wait=True)

        self.epics_pvs['MoveCondenserIn'].put('Done')

    def move_condenser_out(self):
        """Moves the condenser out.
        """
        position = self.epics_pvs['CondenserOutY'].value
        self.epics_pvs['CondenserY'].put(position, wait=True)

        self.epics_pvs['MoveCondenserOut'].put('Done')

    def move_zoneplate_in(self):
        """Moves the zone plate in.
        """
        position = self.epics_pvs['ZonePlateInY'].value
        self.epics_pvs['ZonePlateY'].put(position, wait=True)

        self.epics_pvs['MoveZonePlateIn'].put('Done')

    def move_zoneplate_out(self):
        """Moves the zone plate out.
        """
        position = self.epics_pvs['ZonePlateOutY'].value
        self.epics_pvs['ZonePlateY'].put(position, wait=True)

        self.epics_pvs['MoveZonePlateOut'].put('Done')

    def move_phasering_in(self):
        """Moves the phase ring in.
        """
        position = self.epics_pvs['PhaseRingInX'].value
        self.epics_pvs['PhaseRingX'].put(position, wait=True)
        position = self.epics_pvs['PhaseRingInY'].value
        self.epics_pvs['PhaseRingY'].put(position, wait=True)

        self.epics_pvs['MovePhaseRingIn'].put('Done')

    def move_phasering_out(self):
        """Moves the phase ring out.
        """
        position = self.epics_pvs['PhaseRingOutX'].value
        self.epics_pvs['PhaseRingX'].put(position, wait=True)
        position = self.epics_pvs['PhaseRingOutY'].value
        self.epics_pvs['PhaseRingY'].put(position, wait=True)

        self.epics_pvs['MovePhaseRingOut'].put('Done')