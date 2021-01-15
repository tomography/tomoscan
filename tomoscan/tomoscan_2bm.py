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

    def open_frontend_shutter(self):
        """Opens the shutters to collect flat fields or projections.

        This does the following:

        - Checks if we are in testing mode. If we are, do nothing else opens the 2-BM-A front-end shutter.

        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
        else:
            # Open 2-BM-A front-end shutter
            if not self.epics_pvs['OpenShutter'] is None:
                pv = self.epics_pvs['OpenShutter']
                value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)
                log.info('open shutter: %s, value: %s', pv, value)
                self.epics_pvs['OpenShutter'].put(value, wait=True)
                self.wait_frontend_shutter_open()
                # self.wait_pv(self.epics_pvs['ShutterStatus'], 1)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)

    def open_shutter(self):
        """Opens the shutters to collect flat fields or projections.

        This does the following:

        - Opens the 2-BM-A fast shutter.
        """

        # Open 2-BM-A fast shutter
        if not self.epics_pvs['OpenFastShutter'] is None:
            pv = self.epics_pvs['OpenFastShutter']
            value = self.epics_pvs['OpenFastShutterValue'].get(as_string=True)
            log.info('open fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenFastShutter'].put(value, wait=True)

    def close_frontend_shutter(self):
        """Closes the shutters to collect dark fields.
        This does the following:

        - Closes the 2-BM-A front-end shutter.

        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
        else:
            # Close 2-BM-A front-end shutter
            if not self.epics_pvs['CloseShutter'] is None:
                pv = self.epics_pvs['CloseShutter']
                value = self.epics_pvs['CloseShutterValue'].get(as_string=True)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)
                log.info('close shutter: %s, value: %s', pv, value)
                self.epics_pvs['CloseShutter'].put(value, wait=True)
                self.wait_pv(self.epics_pvs['ShutterStatus'], 0)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)

    def close_shutter(self):
        """Closes the shutters to collect dark fields.
        This does the following:

        - Closes the 2-BM-A fast shutter.
        """

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
        self.epics_pvs['CamAcquire'].put('Done') ###
        self.wait_pv(self.epics_pvs['CamAcquire'], 0) ###
        log.info('set trigger mode: %s', trigger_mode)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            # self.epics_pvs['CamAcquire'].put('Acquire')
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            self.epics_pvs['CamImageMode'].put('Multiple')            
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else: # set camera to external triggering
            # These are just in case the scan aborted with the camera in another state 
            camera_model = self.epics_pvs['CamModel'].get(as_string=True)
            if(camera_model=='Oryx ORX-10G-51S5M'):# 2bma            
                self.epics_pvs['CamTriggerMode'].put('Off', wait=True)   # VN: For FLIR we first switch to Off and then change overlap. any reason of that?                                                 
                self.epics_pvs['CamTriggerSource'].put('Line2', wait=True)
            elif(camera_model=='Grasshopper3 GS3-U3-23S6M'):# 2bmb            
                self.epics_pvs['CamTriggerMode'].put('On', wait=True)     # VN: For PG we need to switch to On to be able to switch to readout overlap mode                                                               
                self.epics_pvs['CamTriggerSource'].put('Line0', wait=True)
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
        
        - Set data directory.
        
        - Opens the front-end shutter.

        - Sets the PSO controller.

        - Creates theta array using list from PSO. 

        - Turns on data capture.
        """
        log.info('begin scan')

        # Set data directory
        file_path = self.epics_pvs['DetectorTopDir'].get(as_string=True) + self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + os.path.sep + self.epics_pvs['UserLastName'].get(as_string=True) + os.path.sep
        self.epics_pvs['FilePath'].put(file_path, wait=True)

        # Call the base class method
        super().begin_scan()
        # Opens the front-end shutter
        self.open_frontend_shutter()
        
        # Confirm angle step is an integer number of encoder pulses
        # Pass the user selected values to the PSO
        self.epics_pvs['PSOstartPos'].put(self.rotation_start, wait=True)
        self.wait_pv(self.epics_pvs['PSOstartPos'], self.rotation_start)
        self.epics_pvs['PSOendPos'].put(self.rotation_stop+self.rotation_step, wait=True)
        self.wait_pv(self.epics_pvs['PSOendPos'], self.rotation_stop+self.rotation_step)
        # Compute and set the motor speed
        time_per_angle = self.compute_frame_time()#+7.2/1000   ##no overlap mode -> time_per_angle=exposure+readout
        motor_speed = self.rotation_step / time_per_angle
        self.epics_pvs['PSOslewSpeed'].put(motor_speed)
        self.wait_pv(self.epics_pvs['PSOslewSpeed'], motor_speed)

        self.epics_pvs['PSOscanDelta'].put(self.rotation_step, wait=True)
        self.wait_pv(self.epics_pvs['PSOscanDelta'], self.rotation_step)

        # Get the number of projections and angle steps calculated by the PSO
        calc_rotation_step = self.epics_pvs['PSOscanDelta'].value
        calc_num_proj = int(self.epics_pvs['PSOcalcProjections'].value)
        # If this is different from the user selected values adjust them
        if calc_rotation_step != self.rotation_step:
            # This should happen most of the time since rotation_step is rounded down to the closest integer
            # number of encoder pulses
            log.warning('PSO changed rotation step from %s to %s', self.rotation_step, calc_rotation_step)
            self.rotation_step = calc_rotation_step
        if calc_num_proj != self.num_angles:
            # This happens rarely an it is a +/-1 change in the number of projections to make sure that
            # after the rotation_step round down we don't pass the user set rotation_stop
            log.warning('PSO changed number of projections from %s to %s', self.num_angles, calc_num_proj)
            self.num_angles = calc_num_proj

        self.epics_pvs['PSOscanControl'].put('Standard')
        self.wait_pv(self.epics_pvs['PSOscanControl'], 0)
        time.sleep(1)

        # # Create theta array
        self.theta = []
        self.theta = self.epics_pvs['ThetaArray'].get(count=int(self.num_angles))
        print(self.theta,self.num_angles)
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

        - Closes shutter.        
        """
        log.info('end scan')
        # Add theta in the hdf file
        self.add_theta()

        # Save the configuration
        # Strip the extension from the FullFileName and add .config
        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        log.info('data save location: %s', full_file_name)
        config_file_root = os.path.splitext(full_file_name)[0]
        self.save_configuration(config_file_root + '.config')
        # Put the camera back in FreeRun mode and acquiring
        # self.set_trigger_mode('FreeRun', 1)
        # self.epics_pvs['CamAcquire'].put('Acquire') ####
        # self.wait_pv(self.epics_pvs['CamAcquire'], 1) ####
        # Set the rotation speed to maximum
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)
        # Move the sample in.  Could be out if scan was aborted while taking flat fields
        self.move_sample_in()
        if self.return_rotation == 'Yes':
        # Reset rotation position by mod 360 , the actual return 
        # to start position is handled by super().end_scan()
            current_angle = self.epics_pvs['Rotation'].get() %360
            self.epics_pvs['RotationSet'].put('Set', wait=True)
            self.epics_pvs['Rotation'].put(current_angle, wait=True)
            self.epics_pvs['RotationSet'].put('Use', wait=True)
        # Call the base class method
        super().end_scan()
        # Close shutter
        self.close_shutter()

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

    def wait_frontend_shutter_open(self, timeout=-1):
        """Waits for the front end shutter to open, or for ``abort_scan()`` to be called.

        While waiting this method periodically tries to open the shutter..

        Parameters
        ----------
        timeout : float
            The maximum number of seconds to wait before raising a ShutterTimeoutError exception.

        Raises
        ------
        ScanAbortError
            If ``abort_scan()`` is called
        ShutterTimeoutError
            If the open shutter has not completed within timeout value.
        """

        start_time = time.time()
        pv = self.epics_pvs['OpenShutter']
        value = self.epics_pvs['OpenShutterValue'].get(as_string = True)
        log.info('open shutter: %s, value: %s', pv, value)
        elapsed_time = 0
        while True:
            if self.epics_pvs['ShutterStatus'].get() == int(value):
                log.warning("Shutter is open in %f s", elapsed_time)
                return
            if not self.scan_is_running:
                exit()
            value = self.epics_pvs['OpenShutterValue'].get()
            time.sleep(1.0)
            current_time = time.time()
            elapsed_time = current_time - start_time
            log.warning("Waiting on shutter to open: %f s", elapsed_time)
            self.epics_pvs['OpenShutter'].put(value, wait=True)
            if timeout > 0:
                if elapsed_time >= timeout:
                   exit()

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
        time_per_angle = self.compute_frame_time()
        collection_time = self.num_angles * time_per_angle
        self.wait_camera_done(collection_time + 60.)
