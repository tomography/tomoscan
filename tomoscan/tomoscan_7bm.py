"""Software for tomography scanning with EPICS at APS beamline 7-BM-B

   Classes
   -------
   TomoScan7BM
     Derived class for tomography scanning with EPICS at APS beamline 7-BM-B
"""
import time
import os
import math
import h5py 
from pathlib import Path
import numpy as np
from epics import PV

from tomoscan import data_management as dm
from tomoscan import TomoScanPSO
from tomoscan import log

EPSILON = .001

class TomoScan7BM(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 7-BM-B

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
        
        # set TomoScan xml files
        self.epics_pvs['CamNDAttributesFile'].put('TomoScanDetectorAttributes.xml')
        self.epics_pvs['FPXMLFileName'].put('TomoScanLayout.xml')
        macro = ('DET=' + self.pv_prefixes['Camera'] + ',' 
                + 'TS=' + self.epics_pvs['Testing'].__dict__['pvname'].replace('Testing', '', 1))
        self.control_pvs['CamNDAttributesMacros'].put(macro)

        # Set the detector running in FreeRun mode
        self.set_trigger_mode('FreeRun', 1)
        
        # Set data directory
        file_path = Path(self.epics_pvs['DetectorTopDir'].get(as_string=True))
        #file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + '-'
                                       + self.epics_pvs['UserLastName'].get(as_string=True) + '-'
                                       + self.epics_pvs['ProposalNumber'].get(as_string=True)) 
        self.epics_pvs['FilePath'].put(str(file_path), wait=True)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Enable over-writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

        #Define PVs we will need from the SampleY  motor for helical scanning, 
        # which is on another IOC
        sample_y_pv_name = self.control_pvs['SampleY'].pvname
        self.epics_pvs['SampleYSpeed']          = PV(sample_y_pv_name + '.VELO')
        self.epics_pvs['SampleYMaxSpeed']       = PV(sample_y_pv_name + '.VMAX')
        self.epics_pvs['SampleYStop']           = PV(sample_y_pv_name + '.STOP')
        

    def open_shutter(self):
        """Opens the shutter to collect flat fields or projections.

        This does the following:

        - Checks if we are in testing mode.  If we are, do nothing.

        - Opens the front end shutter, waiting for it to indicate it is open.
            This is copied from the 2-BM implementation 9/2020

        - Opens the 7-BM-B fast shutter.
        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
            return
        # Open the front end shutter
        if not self.epics_pvs['OpenShutter'] is None:
            pv = self.epics_pvs['OpenShutter']
            value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)
            log.info('open shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenShutter'].put(value, wait=True)
            self.wait_pv(self.epics_pvs['ShutterStatus'], 0)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)
        # Open 7-BM-B fast shutter
        if not self.epics_pvs['OpenFastShutter'] is None:
            pv = self.epics_pvs['OpenFastShutter']
            value = self.epics_pvs['OpenFastShutterValue'].get(as_string=True)
            log.info('open fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenFastShutter'].put(value, wait=True)


    def close_shutter(self):
        """Closes the shutter to collect dark fields and at the end of a scan
        This does the following:

        - Checks if we are in testing mode.  If we are, do nothing

        - Closes the 7-BM-B fast shutter.

        - Closes the beamline shutter.
       """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not closing shutters.')
            return
        # Close 7-BM-B fast shutter; don't wait for it
        if not self.epics_pvs['CloseFastShutter'] is None:
            pv = self.epics_pvs['CloseFastShutter']
            value = self.epics_pvs['CloseFastShutterValue'].get(as_string=True)
            log.info('close fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseFastShutter'].put(value, wait=False)
        # Call the base class method
        if not self.epics_pvs['CloseShutter'] is None:
            pv = self.epics_pvs['CloseShutter']
            value = self.epics_pvs['CloseShutterValue'].get(as_string=True)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)
            log.info('close shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseShutter'].put(value, wait=True)
            self.wait_pv(self.epics_pvs['ShutterStatus'], 1)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)


    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Calls the base class method from tomoscan_pso.py
        - If we are running a helical scan
            - Compute the speed at which the motor needs to move
            - Compute the range over which it must move, checking limits
            - Start the Sample_Y motion
        """
        log.info('begin scan')
        # Call the base class method
        super().begin_scan()
 
        time.sleep(0.1)


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

        log.info('collect projections')
        super().collect_projections()

        log.info('taxi before starting capture')
        # Taxi before starting capture
        self.epics_pvs['Rotation'].put(self.epics_pvs['PSOStartTaxi'].get(), wait=True)

        self.set_trigger_mode('PSOExternal', self.num_angles)

        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')

        # If this is a helical scan, start Sample_Y moving
        if self.epics_pvs['ScanType'] == 'Helical':
            import pdb; pdb.set_trace()
            end_Y, speed_Y = self.compute_helical_motion()
            self.epics_pvs('SampleYSpeed').put(speed_Y)
            self.epics_pvs('Sample_Y').put(end_Y)

        # Need to wait a short time for AcquireBusy to change to 1
        time.sleep(0.5)

        # Start fly scan
        log.info('start fly scan')
        self.epics_pvs['Rotation'].put(self.epics_pvs['PSOEndTaxi'].get())
        time_per_angle = self.compute_frame_time()
        collection_time = self.num_angles * time_per_angle
        self.wait_camera_done(collection_time + 30.)
        

    def abort_scan(self):
        """Aborts a scan that is running and performs the operations 
        needed when a scan is aborted.

        This function mostly calls the super class.
        It also stops vertical motion if the scan is helical.
        """
        super().abort_scan()
        
        log.info('stop vertical motion for helical scan')
        self.epics_pvs['SampleYStop'].put(1, wait=True)
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)


    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        Mostly handled by the super class.
        Logic here to reset the SampleY motor speed
        """
        log.info('end scan')
        log.info('reset SampleY motor speed')
        self.epics_pvs['SampleYSpeed'].put(self.epics_pvs['SampleYMaxSpeed'].get())

        # Call the base class method
        super().end_scan()


    def compute_helical_motion():
        """Computes the speed and magnitude from SampleY motion for helical
        scans.
        """
        vertical_pixels_per_rotation = self.epics_pvs['PixelsYPer360Degrees'].get()
        pixel_size = self.epics_pvs['ImagePixelSize']
        angle_range = self.epics_pvs['RotationStep'].get() * (self.epics_pvs['NumAngles'] - 1)
        rotation_speed = self.epics_pvs['RotationSpeed'].get()
        speed_Y = np.abs(vertical_pixels_per_rotation * pixel_size / 360. * rotation_speed)
        end_Y = (self.epics_pvs['SampleY'].get() + angle_range / 360. 
                    * vertical_pixels_per_rotation * pixel_size)
        #Arbitrarily add 5 s to the y motion to account for timing imperfections
        end_Y += np.sign(vertical_pixels_per_rotation) * speed_Y * 5.0
        return speed_Y, end_Y

 
    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode for the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
            This is used to set the ``NumImages`` PV of the camera.
        """
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamAcquire'].put('Acquire')
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else: # set camera to external triggering
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            ext_source = str(self.epics_pvs['ExternalTriggerSource'].get())
            self.epics_pvs['CamTriggerSource'].put(ext_source, wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)

            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateEnable'].put(0)

            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)

            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 1)


    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Add theta to the raw data file. 

        - Close the shutter

        - Calls the base class method.
        """
        log.info('end scan')

        # Close the shutter
        self.close_shutter()

        # Stop the file plugin, though it should be done already
        self.epics_pvs['FPCapture'].put('Done')
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)

        # Add theta in the hdf file
        self.add_theta()

        # Copy file to the analysis computer, if desired
        self.auto_copy_data()

        # Call the base class method
        super().end_scan()


    def add_theta(self):
        """Add theta at the end of a scan.
        """
        log.info('add theta')
        self.theta = np.linspace(self.rotation_start, self.rotation_stop, self.num_angles)
        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        file_name_path = Path(full_file_name)
        if os.path.exists(full_file_name):
            try:
                f = h5py.File(full_file_name, "a")
                with f:
                    try:
                        if self.theta is not None:
                            theta_ds = f.create_dataset('/exchange/theta', data = self.theta)
                    except:
                        log.error('Add theta: Failed accessing: %s', full_file_name)
                        traceback.print_exc(file=sys.stdout)
            except OSError:
                log.error('Add theta aborted')
        else:
            log.error('Failed adding theta. %s file does not exist', full_file_name)


    def wait_pv(self, epics_pv, wait_val, timeout=np.inf, delta_t=0.01):
        """Wait on a pv to be a value until max_timeout (default forever)
           delay for pv to change
        """
        time.sleep(delta_t)
        start_time = time.time()
        while time.time() - start_time < timeout:
            pv_val = epics_pv.get()
            if isinstance(pv_val, float):
                if abs(pv_val - wait_val) < EPSILON:
                    return True
            if pv_val == wait_val:
                return True
            time.sleep(delta_t)
        else:
            log.error('  *** ERROR: PV TIMEOUT ***')
            log.error('  *** wait_pv(%s, %d, %5.2f reached max timeout. Return False',
                          epics_pv.pvname, wait_val, timeout)
            return False

    def auto_copy_data(self):
        '''Copies data from detector computer to analysis computer.
        '''
        # Copy raw data to data analysis computer    
        if self.epics_pvs['CopyToAnalysisDir'].get():
            log.info('Automatic data trasfer to data analysis computer is enabled.')
            full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
            remote_analysis_dir = self.epics_pvs['RemoteAnalysisDir'].get(as_string=True)
            dm.scp(full_file_name, remote_analysis_dir)
        else:
            log.warning('Automatic data trasfer to data analysis computer is disabled.')
