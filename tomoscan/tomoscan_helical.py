"""Software for tomography scanning with EPICS at APS beamline 7-BM-B

   Classes
   -------
   TomoScanHelical
     Derived class for tomography scanning with EPICS using Aerotech PSO in helical mode
"""
import time
import os
import math
import h5py 
from pathlib import Path
import numpy as np
from epics import PV

from tomoscan import data_management as dm
from tomoscan.tomoscan_pso import TomoScanPSO
from tomoscan import log

EPSILON = .001

class TomoScanHelical(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS using Aerotech PSO in helical mode

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

        #Define PVs we will need from the SampleY  motor for helical scanning, 
        # which is on another IOC
        sample_y_pv_name = self.control_pvs['SampleY'].pvname
        self.epics_pvs['SampleYSpeed']          = PV(sample_y_pv_name + '.VELO')
        self.epics_pvs['SampleYMaxSpeed']       = PV(sample_y_pv_name + '.VMAX')
        self.epics_pvs['SampleYStop']           = PV(sample_y_pv_name + '.STOP')
        self.epics_pvs['SampleYHLM']            = PV(sample_y_pv_name + '.HLM')
        self.epics_pvs['SampleYLLM']            = PV(sample_y_pv_name + '.LLM')


    def collect_projections(self):
        """Collects projections in fly scan mode.

        This does the following:

        - Call the superclass collect_projections() function

        - Taxi to the start position

        - Set the trigger mode on the camera
   
        - Move the stage to the end position

        - Computes and sets the speed of the rotation motor so that it reaches the next projection
          angle just after the current exposure and readout are complete.

        - These will be used by the PSO to calculate the Taxi distance and rotary stage acceleration.

        - Starts the file plugin capturing in stream mode.

        - Starts the camera acquiring in external trigger mode.

        - Starts the PSOfly.

        - Wait on the PSO done.
        """

        #Call the collect_projections() function from the TomoScan base class
        log.info('collect projections')
        
        if self.num_angles==0:
            return

        super(TomoScanPSO, self).collect_projections()

        log.info('taxi before starting capture')
        # Taxi before starting capture
        self.epics_pvs['Rotation'].put(self.epics_pvs['PSOStartTaxi'].get(), wait=True)

        self.set_trigger_mode('PSOExternal', self.num_angles)

        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')

        # If this is a helical scan, start Sample_Y moving
        if self.epics_pvs['ScanType'].get(as_string=True) == 'Helical':
            self.program_helical_motion()

        # Need to wait a short time for AcquireBusy to change to 1
        time.sleep(0.5)

        # Start fly scan
        log.info('start fly scan')
        self.epics_pvs['Rotation'].put(self.epics_pvs['PSOEndTaxi'].get())
        time_per_angle = self.compute_frame_time()
        collection_time = self.num_angles * time_per_angle
        self.wait_camera_done(collection_time + 30.)
        

    def abort_scan(self):
        """Performs operations needed if a scan is aborted.
        
        Mostly handled by super class.
        Logic here to stop the Y motor.
        """
        super().abort_scan()
        log.info('helical: abort scan')
        if self.epics_pvs['ScanType'].get(as_string=True) == 'Helical':
            log.info('helical: stop vertical motion')
            self.epics_pvs['SampleYStop'].put(1)


    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        Mostly handled by the super class.
        Logic here to reset the SampleY motor speed and go back to start position
        """
        log.info('end scan')

        # If this is a helical scan, stop Sample_Y moving
        if self.epics_pvs['ScanType'].get(as_string=True) == 'Helical':
            log.info('helical: reset vertical speed and position')
            self.epics_pvs['SampleYSpeed'].put(self.epics_pvs['SampleYMaxSpeed'].get())
            log.info('helical: bring SampleY motor back to start position')
            self.epics_pvs['SampleY'].put(self.epics_pvs['SampleInY'].get())

        # Call the base class method
        super().end_scan()


    def program_helical_motion(self):
        """Computes the speed and magnitude from SampleY motion for helical
        scans.
        """
        y_pixels_per_rotation = self.epics_pvs['PixelsYPer360Deg'].get()
        pixel_size = self.epics_pvs['ImagePixelSize'].get() / 1000.
        angle_range = self.epics_pvs['RotationStep'].get() * (self.epics_pvs['NumAngles'].get() - 1)
        rotation_speed = self.epics_pvs['RotationSpeed'].get()
        speed_Y = np.abs(y_pixels_per_rotation * pixel_size / 360. * rotation_speed)
        end_Y = (self.epics_pvs['SampleY'].get() + angle_range / 360. 
                    * y_pixels_per_rotation * pixel_size)
        #Arbitrarily add 5 s to the y motion to account for timing imperfections
        end_Y += np.sign(y_pixels_per_rotation) * speed_Y * 5.0
        #Check limits
        if end_Y > self.epics_pvs['SampleYHLM'].get() or end_Y < self.epics_pvs['SampleYLLM'].get():
            log.error('helical: Y range would fall outside SampleY motor limits')
            self.epics_pvs['AbortScan'].put(1)
        self.epics_pvs['SampleYSpeed'].put(speed_Y)
        self.epics_pvs['SampleY'].put(end_Y)
