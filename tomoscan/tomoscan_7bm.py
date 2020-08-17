"""Software for tomography scanning with EPICS at APS beamline 7-BM-B

   Classes
   -------
   TomoScan7BM
     Derived class for tomography scanning with EPICS at APS beamline 7-BM-B
"""
import time
import os
import h5py 
from pathlib import Path

from tomoscan import TomoScan
from tomoscan import log

EPSILON = .001

class TomoScan7BM(TomoScan):
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
        # Set the detector running in FreeRun mode
        self.set_trigger_mode('FreeRun', 1)
        
        # Set data directory
        file_path = Path(self.epics_pvs['DetectorTopDir'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + '-'
                                       + self.epics_pvs['UserLastName'].get(as_string=True) + '-'
                                       + self.epics_pvs['ProposalNumber'].get(as_string=True)) 
        self.epics_pvs['FilePath'].put(str(file_path), wait=True)

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

        - Closes the 7-BM-B fast shutter.

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
        - 
        """
        log.info('begin scan')
        # Call the base class method
        super().begin_scan()
 
        # Program the stage driver to provide PSO pulses
        program_PSO()

        # Confirm angle step is an integer number of encoder pulses
        # Pass the user selected values to the PSO
        self.epics_pvs['PSOstartPos'].put(self.rotation_start, wait=True)
        self.wait_pv(self.epics_pvs['PSOstartPos'], self.rotation_start)
        self.epics_pvs['PSOendPos'].put(self.rotation_stop, wait=True)
        self.wait_pv(self.epics_pvs['PSOendPos'], self.rotation_stop)
        # Compute and set the motor speed
        time_per_angle = self.compute_frame_time()
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

        # Compute total number of frames to capture
        self.total_images = self.num_angles
        if self.dark_field_mode != 'None':
            self.total_images += self.num_dark_fields
        if self.dark_field_mode == 'Both':
            self.total_images += self.num_dark_fields
        if self.flat_field_mode != 'None':
            self.total_images += self.num_flat_fields
        if self.flat_field_mode == 'Both':
            self.total_images += self.num_flat_fields
        # Set the total number of frames to capture and start capture on file plugin
        self.epics_pvs['FPNumCapture'].put(self.total_images, wait=True)
        self.epics_pvs['FPCapture'].put('Capture')

    def program_PSO(self):



            self.control_pvs['PSOscanDelta']       = PV(prefix + 'scanDelta')
            self.control_pvs['PSOstartPos']        = PV(prefix + 'startPos')
            self.control_pvs['PSOendPos']          = PV(prefix + 'endPos')
            self.control_pvs['PSOslewSpeed']       = PV(prefix + 'slewSpeed')
            self.control_pvs['PSOtaxi']            = PV(prefix + 'taxi')
            self.control_pvs['PSOfly']             = PV(prefix + 'fly')
            self.control_pvs['PSOscanControl']     = PV(prefix + 'scanControl')
            self.control_pvs['PSOcalcProjections'] = PV(prefix + 'numTriggers')        
            self.control_pvs['ThetaArray']         = PV(prefix + 'motorPos.AVAL')


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
        # Add theta in the hdf file
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


class AerotechDriver():
    def __init__(self, motor='7bmb1:aero:m1', asynRec='7bmb1:PSOFly1:cmdWriteRead', axis='Z', PSOInput=3,encoder_multiply=1e5):
        self.motor = epics.Motor(motor)
        self.asynRec = epics.PV(asynRec + '.BOUT')
        self.axis = axis
        self.PSOInput = PSOInput
        self.encoder_multiply = encoder_multiply

    def program_PSO(self):
        '''Performs programming of PSO output on the Aerotech driver.
        '''
        #Place the motor at the position where the first PSO pulse should be triggered
        self.motor.move(PSO_positions[0], wait=True)

        #Make sure the PSO control is off
        self.asynRec.put('PSOCONTROL %s RESET' % self.axis, wait=True, timeout=300.0)
        time.sleep(0.05)
      
        ## initPSO: commands to the Ensemble to control PSO output.
        # Everything but arming and setting the positions for which pulses will occur.
        #Set the output to occur from the I/O terminal on the controller
        self.asynRec.put('PSOOUTPUT %s CONTROL 1' % self.axis, wait=True, timeout=300.0)
        time.sleep(0.05)
        #Set a pulse 10 us long, 20 us total duration, so 10 us on, 10 us off
        self.asynRec.put('PSOPULSE %s TIME 20,10' % self.axis, wait=True, timeout=300.0)
        time.sleep(0.05)
        #Set the pulses to only occur in a specific window
        self.asynRec.put('PSOOUTPUT %s PULSE WINDOW MASK' % self.axis, wait=True, timeout=300.0)
        time.sleep(0.05)
        #Set which encoder we will use.  3 = the MXH (encoder multiplier) input, which is what we generally want
        self.asynRec.put('PSOTRACK %s INPUT %d' % (self.axis, self.PSOInput), wait=True, timeout=300.0)
        time.sleep(0.05)
        #Set the distance between pulses.  Do this in encoder counts.
        self.asynRec.put('PSODISTANCE %s FIXED %d' % (self.axis, delta_encoder_counts), wait=True, timeout=300.0)
        time.sleep(0.05)
        #Which encoder is being used to calculate whether we are in the window.  1 for single axis
        self.asynRec.put('PSOWINDOW %s 1 INPUT %d' % (self.axis, self.PSOInput), wait=True, timeout=300.0)
        time.sleep(0.05)

        #Calculate window function parameters.  Must be in encoder counts, and is 
        #referenced from the stage location where we arm the PSO.  We are at that point now.
        #We want pulses to start at start - delta/2, end at end + delta/2.  
        range_start = -round(delta_encoder_counts / 2) * overall_sense
        range_length = PSO_positions.shape[0] * delta_encoder_counts
        #The start of the PSO window must be < end.  Handle this.
        if overall_sense > 0:
            window_start = range_start
            window_end = window_start + range_length
        else:
            window_end = range_start
            window_start = window_end - range_length
        #Remember, the window settings must be in encoder counts
        self.asynRec.put('PSOWINDOW %s 1 RANGE %d,%d' % (self.axis, window_start-5, window_end+5), wait=True, timeout=300.0)
        #print('PSOWINDOW %s 1 RANGE %d,%d' % (self.axis, window_start, window_end))
        #Arm the PSO
        time.sleep(0.05)
        self.asynRec.put('PSOCONTROL %s ARM' % self.axis, wait=True, timeout=300.0)
        #Move to the actual start position and set the motor speed
        self.motor.move(motor_start, wait=True)
        self.motor.put('VELO', speed, wait=True)

    def cleanup_PSO(self):
        '''Cleanup activities after a PSO scan. 
        Turns off PSO and sets the speed back to default.
        '''
        log.info('Cleaning up PSO programming and setting to retrace speed.')
        self.asynRec.put('PSOWINDOW %s OFF' % self.axis, wait=True)
        self.asynRec.put('PSOCONTROL %s OFF' % self.axis, wait=True)
        self.motor.put('VELO', self.default_speed, wait=True)
 

driver = AerotechDriver(motor='7bmb1:aero:m3', asynRec='7bmb1:PSOFly3:cmdWriteRead', axis='A', PSOInput=3, encoder_multiply=float(2**15)/0.36)


def _compute_senses():
    '''Computes the senses of motion: encoder direction, motor direction,
    user direction, overall sense.
    '''
    # Encoder direction compared to dial coordinates.  Hard code this; could ask controller
    encoderDir = -1
    #Get motor direction (dial vs. user)
    motor_dir = -1 if driver.motor.direction else 1
    #Figure out whether motion is in positive or negative direction in user coordinates
    global user_direction
    user_direction = 1 if req_end > req_start else -1
    #Figure out overall sense: +1 if motion in + encoder direction, -1 otherwise
    global overall_sense
    overall_sense = user_direction * motor_dir * encoderDir

    
def compute_positions():
    '''Computes several parameters describing the fly scan motion.
    These calculations are for tomography scans, where for N images we need N pulses.
    Moreover, we base these on the number of images, not the delta between.
    '''
    global actual_end, delta_egu, delta_encoder_counts, motor_start, motor_end, PSO_positions
    global proj_positions
    _compute_senses()
    #Get the distance needed for acceleration = 1/2 a t^2 = 1/2 * v * t
    motor_accl_time = driver.motor.acceleration    #Acceleration time in s
    accel_dist = motor_accl_time * speed / 2.0  

    #Compute the actual delta to keep things at an integral number of encoder counts
    raw_delta_encoder_counts = (abs(req_end - req_start) 
                                    / ((num_proj - 1) * num_images_per_proj) * driver.encoder_multiply)
    delta_encoder_counts = round(raw_delta_encoder_counts)
    if abs(raw_delta_encoder_counts - delta_encoder_counts) > 1e-4:
        log.warning('  *** *** *** Requested scan would have used a non-integer number of encoder pulses.')
        log.warning('  *** *** *** Calculated # of encoder pulses per step = {0:9.4f}'.format(raw_delta_encoder_counts))
        log.warning('  *** *** *** Instead, using {0:d}'.format(delta_encoder_counts))
    delta_egu = delta_encoder_counts / driver.encoder_multiply
                
    #Make taxi distance an integral number of measurement deltas >= accel distance
    #Add 1/2 of a delta to ensure that we are really up to speed.
    taxi_dist = (math.ceil(accel_dist / delta_egu) + 0.5) * delta_egu
    motor_start = req_start - taxi_dist * user_direction
    motor_end = req_end + taxi_dist * user_direction
    
    #Where will the last point actually be?
    actual_end = req_start + (num_proj * num_images_per_proj- 1) * delta_egu * user_direction
    end_proj = req_start + (num_proj - 1) * delta_egu * user_direction * num_images_per_proj
    PSO_positions = np.linspace(req_start, actual_end, num_proj * num_images_per_proj)
    proj_positions = np.linspace(req_start, end_proj, num_proj) 
    log_info()

    
def set_default_speed(speed):
    log.info('Setting retrace speed on motor to {0:f} deg/s'.format(float(speed)))
    driver.default_speed = speed


def program_PSO():
    '''Cause the Aerotech driver to program its PSO.
    '''
    log.info('  *** *** Programming motor')
    driver.program_PSO()


def cleanup_PSO():
    driver.cleanup_PSO()

def log_info():
    log.warning('  *** *** Positions for fly scan.')
    log.info('  *** *** *** Motor start = {0:f}'.format(req_start))
    log.info('  *** *** *** Motor end = {0:f}'.format(actual_end))
    log.info('  *** *** *** # Points = {0:4d}'.format(num_proj))
    log.info('  *** *** *** Degrees per image = {0:f}'.format(delta_egu))
    log.info('  *** *** *** Degrees per projection = {0:f}'.format(delta_egu / num_images_per_proj))
    log.info('  *** *** *** Encoder counts per image = {0:d}'.format(delta_encoder_counts))


    def pso_init(params):
        '''Initialize calculations.
        '''
        global req_start, req_end, num_proj, num_images_per_proj, speed
        req_start = params.sample_rotation_start
        req_end = params.sample_rotation_end
        num_proj = params.num_projections
        if params.recursive_filter:
            num_images_per_proj = params.recursive_filter_n_images
        else:
            num_images_per_proj = 1
        speed = params.slew_speed
        driver.default_speed = params.retrace_speed
        compute_positions()


def fly(global_PVs, params):
    angular_range =  params.sample_rotation_end -  params.sample_rotation_start
    flyscan_time_estimate = angular_range / params.slew_speed
    log.warning('  *** Fly Scan Time Estimate: %4.2f minutes' % (flyscan_time_estimate/60.))
    #Trigger fly motion to start.  Don't wait for it, since it takes time.
    start_time = time.time()
    driver.motor.move(motor_end, wait=False)
    time.sleep(1)
    old_image_counter = 0
    expected_framerate = driver.motor.slew_speed / delta_egu
    #Monitor the motion to make sure we aren't stuck.
    i = 0
    while time.time() - start_time < 1.5 * flyscan_time_estimate:
        i += 1
        if i % 10 == 0:
            log.info('  *** *** Sample rotation at angle {:f}'.format(driver.motor.readback))
        time.sleep(2)
        if not driver.motor.moving:
            log.info('  *** *** Sample rotation stopped moving.')
            if abs(driver.motor.drive - motor_end) > 1e-2:
                log.error('  *** *** Sample rotation ended but not at right position!')
                raise ValueError
            else:
                log.info('  *** *** Stopped at correct position.')
                break
        #Make sure we're actually getting frames.
        current_image_counter = global_PVs['Cam1_NumImagesCounter'].get()
        if current_image_counter - old_image_counter < 0.1 * expected_framerate:
            log.error('  *** *** Not collecting frames!')
            time.sleep(0.5)
            if driver.motor.moving:
                raise ValueError 
        else:
            old_image_counter = current_image_counter
    else:
        log.warning('  *** *** Fly motion timed out!')
        raise ValueError
