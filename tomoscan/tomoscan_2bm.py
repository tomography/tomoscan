"""Software for tomography scanning with EPICS at APS beamline 2-BM-A

   Classes
   -------
   TomoScan2BM
     Derived class for tomography scanning with EPICS at APS beamline 2-BM-A
"""
import time
import os
import h5py 

from tomoscan import TomoScan
from tomoscan import log

EPSILON = .001

class TomoScan2BM(TomoScan):
    """Derived class used for tomography scanning with EPICS at APS beamline 2-BM-A

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
        
        # Set data directory
        file_path = self.epics_pvs['DetectorTopDir'].get(as_string=True) + self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + os.path.sep + self.epics_pvs['UserLastName'].get(as_string=True) + os.path.sep
        self.epics_pvs['FilePath'].put(file_path, wait=True)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Disable overw writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

    def open_shutter(self):
        """Opens the shutter to collect flat fields or projections.

        This does the following:

        - Calls the base class method.

        - Opens the 2-BM-A fast shutter.
        """

        # Call the base class method
        super().open_shutter()
        # Open 2-BM-A fast shutter
        if not self.epics_pvs['OpenFastShutter'] is None:
            pv = self.epics_pvs['OpenFastShutter']
            value = self.epics_pvs['OpenFastShutterValue'].get(as_string=True)
            log.info('open fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenFastShutter'].put(value, wait=True)

    def close_shutter(self):
        """Closes the shutter to collect dark fields.
        This does the following:

        - Calls the base class method.

        - Closes the 2-BM-A fast shutter.

       """
         # Call the base class method
        super().close_shutter()
        # Close 2-BM-A fast shutter
        if not self.epics_pvs['CloseFastShutter'] is None:
            pv = self.epics_pvs['CloseFastShutter']
            value = self.epics_pvs['CloseFastShutterValue'].get(as_string=True)
            log.info('close fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseFastShutter'].put(value, wait=True)

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode SIS3820 and the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
            This is used to set the ``NumImages`` PV of the camera.
        """
        log.info('set trigger mode: %s', trigger_mode)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            self.epics_pvs['CamAcquire'].put('Acquire')
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else: # set camera to external triggering
            # These are just in case the scan aborted with the camera in another state
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamTriggerSource'].put('Line2', wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)

            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateEnable'].put(0)

            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 1)

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
        self.wait_pv(self.epics_pvs['CamAcquire'], 1)
        # Wait for detector and file plugin to be ready
        time.sleep(0.5)
        frame_time = self.compute_frame_time()
        collection_time = frame_time * num_frames
        self.wait_camera_done(collection_time + 5.0)

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Calls the base class method.

        """
        log.info('begin scan')
        # Call the base class method
        super().begin_scan()
        
        # Compute total number of frames to capture
        num_dark_fields = self.epics_pvs['NumDarkFields'].value
        dark_field_mode = self.epics_pvs['DarkFieldMode'].get(as_string=True)
        num_flat_fields = self.epics_pvs['NumFlatFields'].value
        flat_field_mode = self.epics_pvs['FlatFieldMode'].get(as_string=True)
        num_angles = self.epics_pvs['NumAngles'].value
        num_images = num_angles
        if dark_field_mode not in ('None'):
            num_images += num_dark_fields;
        if dark_field_mode == 'Both':
            num_images += num_dark_fields;
        if flat_field_mode not in ('None'):
            num_images += num_flat_fields;
        if flat_field_mode == 'Both':
            num_images += num_flat_fields;
        # Set the total number of frames to capture and start capture on file plugin
        self.epics_pvs['FPNumCapture'].put(self.total_images, wait=True)
        self.epics_pvs['FPCapture'].put('Capture')

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Add theta to the raw data file. 

        - Calls ``save_configuration()``.

        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.
        """
        log.info('end scan')
        # Add theta 
        self.theta = []
        self.theta = self.epics_pvs['ThetaArray'].get(count=int(self.num_angles))
        self.add_theta()

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
        # Move the sample in.  Could be out if scan was aborted while taking flat fields
        self.move_sample_in()
        # Call the base class method
        super().end_scan()


    def add_theta(self):
        """Add theta at the end of a scan.
        """
        log.info('add theta')

        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        if os.path.exists(full_file_name):
            try:
                f = h5py.File(full_file_name, "a")
                with f:
                    try:
                        if self.theta is not None:
                            theta_ds = f.create_dataset('/exchange/theta', (len(self.theta),))
                            theta_ds[:] = self.theta[:]
                    except:
                        log.error('Add theta: Failed accessing: %s', full_file_name)
                        traceback.print_exc(file=sys.stdout)
            except OSError:
                log.error('Add theta aborted')
        else:
            log.error('Failed adding theta. %s file does not exist', full_file_name)

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

    def collect_projections(self):
        """Collects projections in fly scan mode.

        This does the following:

        - Set the rotation motor position specified by the ``RotationStart`` PV in the
          PSOstartPos.

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
        # Compute and set the motor speed
        time_per_angle = self.compute_frame_time()
        motor_speed = self.rotation_step / time_per_angle

        self.epics_pvs['PSOstartPos'].put(self.rotation_start)
        self.epics_pvs['PSOendPos'].put(self.rotation_stop)
        self.epics_pvs['PSOslewSpeed'].put(motor_speed)
        self.epics_pvs['PSOscanDelta'].put(self.rotation_step)

        calc_num_proj = self.epics_pvs['PSOcalcProjections'].value

        if calc_num_proj != self.num_angles:
            log.warning('PSO changed number of projections from: %s to: %s', self.num_angles, int(calc_num_proj))
            self.num_angles = calc_num_proj
        self.epics_pvs['PSOscanControl'].put('Standard')

        log.info('taxi before starting capture')
        # Taxi before starting capture
        self.epics_pvs['PSOtaxi'].put(1, wait=True)
        self.wait_pv(self.epics_pvs['PSOtaxi'], 0)

        self.set_trigger_mode('PSOExternal', self.num_angles)
        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')
        self.wait_pv(self.epics_pvs['CamAcquire'], 1)
        log.info('start fly scan')
        # Start fly scan
        self.epics_pvs['PSOfly'].put(1) #, wait=True)
        # wait for acquire to finish
        # wait_camera_done instead of the wait_pv enabled the counter update
        # self.wait_pv(self.epics_pvs['PSOfly'], 0)
        collection_time = self.num_angles * time_per_angle
        self.wait_camera_done(collection_time + 60.)
