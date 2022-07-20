"""Software for tomography scanning with EPICS

   Classes
   -------
   TomoScanSTEP
     Derived class for tomography scanning with EPICS implementing step scan
"""

import time
import os
import math
import numpy as np
from datetime import timedelta
from tomoscan.tomoscan import TomoScan
from tomoscan import log

class TomoScanSTEP(TomoScan):
    """Derived class used for tomography scanning with EPICS implementing step scan

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

    def collect_static_frames(self, num_frames):
        """Collects num_frames images in "Internal" trigger mode for dark fields and flat fields.

        Parameters
        ----------
        num_frames : int
            Number of frames to collect.
        """
        # This is called when collecting dark fields or flat fields

        log.info('collect static frames: %d', num_frames)
        self.set_trigger_mode('Internal', num_frames)
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Wait for detector and file plugin to be ready
        time.sleep(0.5)
        frame_time = self.compute_frame_time()
        collection_time = frame_time * num_frames
        self.wait_camera_done(collection_time + 5.0)

    def collect_dark_fields(self):
        """Collects dark field images.
        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumDarkFields`` PV.
        """

        log.info('collect dark fields')
        super().collect_dark_fields()
        self.collect_static_frames(self.num_dark_fields)

    def collect_flat_fields(self):
        """Collects flat field images.
        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumFlatFields`` PV.
        """
        log.info('collect flat fields')
        super().collect_flat_fields()
        self.collect_static_frames(self.num_flat_fields)

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Calls the base class method.

        - Set the HDF plugin.
        """

        log.info('begin scan')
        # Call the base class method
        super().begin_scan()
        
        # Set angles for the interlaced scan
        if(self.epics_pvs['InterlacedScan'].get(as_string=True)=='Yes'):
            interlacedfilename = self.epics_pvs['InterlacedFileName'].get(as_string=True)
            try:
                self.theta = np.load(interlacedfilename)                
                # update angles and number of frames to be captured and collected
                self.total_images -= self.num_angles-len(self.theta)
                self.num_angles = len(self.theta)                
                # print some information about angles
                stheta = np.sort(self.theta)
                log.info('file with interlaced angles %s', interlacedfilename)
                log.info('loaded %d interlaced angles',self.num_angles)
                log.info('min angle %f',stheta[0])
                log.info('max angle %f',stheta[-1])
                log.info('min distance between neigbouring sorted angles %f',np.amin(np.abs(stheta[1::2]-stheta[::2])))
                log.info('max distance between neigbouring sorted angles %f',np.amax(np.abs(stheta[1::2]-stheta[::2])))                
            except:
                log.error('%s file with interlaced angles is not valid', interlacedfilename)
                self.theta = []
                self.abort_scan()
                return                
        else:
                self.theta = self.rotation_start + np.arange(self.num_angles) * self.rotation_step

        self.epics_pvs['FPNumCapture'].put(self.total_images, wait=True)
        self.epics_pvs['FPCapture'].put('Capture')

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Calls ``save_configuration()``.

        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.
        """
        log.info('end scan')
        # Save the configuration
        # Strip the extension from the FullFileName and add .config
        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        log.info('data save location: %s', full_file_name)
        config_file_root = os.path.splitext(full_file_name)[0]
        self.save_configuration(config_file_root + '.config')

        # Put the camera back in FreeRun mode and acquiring
        self.set_trigger_mode('FreeRun', 1)

        # Set the rotation speed to maximum
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)
        # self.cleanup_PSO()

        # Move the sample in.  Could be out if scan was aborted while taking flat fields
        self.move_sample_in()

        # Call the base class method
        super().end_scan()

    def collect_projections(self):
        """Collects projections in fly scan mode.

        This does the following:

        - Call the superclass collect_projections() function.

        - Set the trigger mode on the camera.
   
        - Set the camera in acquire mode.

        - Starts the camera acquiring in software trigger mode.

        - Update scan status.
        """

        log.info('collect projections')
        super().collect_projections()

        self.set_trigger_mode('Software', self.num_angles)
           
        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Need to wait a short time for AcquireBusy to change to 1
        time.sleep(0.5)
        self.epics_pvs['HDF5Location'].put(self.epics_pvs['HDF5ProjectionLocation'].value)
        self.epics_pvs['FrameType'].put('Projection')

        start_time = time.time()
        stabilization_time = self.epics_pvs['StabilizationTime'].get()
        log.info("stabilization time %f s", stabilization_time)
        for k in range(self.num_angles):
            if(self.scan_is_running):
                log.info('angle %d: %f', k, self.theta[k])
                self.epics_pvs['Rotation'].put(self.theta[k], wait=True)            
                time.sleep(stabilization_time)
                self.epics_pvs['CamTriggerSoftware'].put(1)    
                self.wait_pv(self.epics_pvs['CamNumImagesCounter'], k+1, 60)
                self.update_status(start_time)
        
        # wait until the last frame is saved (not needed)
        time.sleep(0.5)        
        self.update_status(start_time)                

    def wait_pv(self, epics_pv, wait_val, timeout=-1):
        """Wait on a pv to be a value until max_timeout (default forever)
           delay for pv to change
        """

        time.sleep(.01)
        start_time = time.time()
        while True:
            pv_val = epics_pv.get()
            if isinstance(pv_val, float):
                if abs(pv_val - wait_val) < EPSILON:
                    return True
            if pv_val != wait_val:
                if timeout > -1:
                    current_time = time.time()
                    diff_time = current_time - start_time
                    if diff_time >= timeout:
                        log.error('  *** ERROR: DROPPED IMAGES ***')
                        log.error('  *** wait_pv(%s, %d, %5.2f reached max timeout. Return False',
                                      epics_pv.pvname, wait_val, timeout)
                        return False
                time.sleep(.01)
            else:
                return True
