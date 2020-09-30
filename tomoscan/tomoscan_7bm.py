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
        
        #Add in the acceleration time PV for the rotation motor for PSO calculations
        rotation_pv_name = self.control_pvs['Rotation'].pvname
        self.control_pvs['RotationAccelTime']      = PV(rotation_pv_name + '.ACCL')
        self.epics_pvs['RotationAccelTime'] = self.control_pvs['RotationAccelTime']

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

        - Checks if we are in testing mode.  If we are, do nothing.

        - Opens the front end shutter, waiting for it to indicate it is open.
            This is copied from the 2-BM implementation 9/2020

        - Opens the 2-BM-A fast shutter.
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
        """Closes the shutter to collect dark fields.
        This does the following:

        - Checks if we are in testing mode.  If we are, do nothing

        - Calls the base class method.

        - Closes the 7-BM-B fast shutter.

       """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not closing shutters.')
            return
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
        # Close 7-BM-B fast shutter
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
        # Stop acquisition if we are acquiring
        self.epics_pvs['CamAcquire'].put('Done', wait=True)
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
            cam_trig_source = self.epics_pvs['ExternalTriggerSource'].get(as_string=True)
            self.epics_pvs['CamTriggerSource'].put(cam_trig_source, wait=True)
            self.epics_pvs['CamTriggerOverlap'].put(1, wait=True)
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
        - Sets the speed of the rotation motor
        - Computes the delta theta, start and stop motor positions for the scan
        - Programs the Aerotech driver to provide pulses at the right positions
        """
        log.info('begin scan')
        # Call the base class method
        super().begin_scan()
 
        # Compute the time for each frame
        time_per_angle = self.compute_frame_time()
        self.motor_speed = self.rotation_step / time_per_angle
        time.sleep(0.1)

        # Program the stage driver to provide PSO pulses
        self.compute_positions()
        self.program_PSO()

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
        # Close the shutter
        self.close_shutter()
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
        self.cleanup_PSO()
        # Move the sample in.  Could be out if scan was aborted while taking flat fields
        self.move_sample_in()
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
        self.epics_pvs['Rotation'].put(self.epics_pvs['startTaxi'].get(), wait=True)

        self.set_trigger_mode('PSOExternal', self.num_angles)
        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')
        self.wait_pv(self.epics_pvs['CamAcquire'], 1)
        log.info('start fly scan')
        # Start fly scan
        self.epics_pvs['Rotation'].put(self.epics_pvs['endTaxi'].get())
        # wait for acquire to finish
        # wait_camera_done instead of the wait_pv enabled the counter update
        # self.wait_pv(self.epics_pvs['PSOfly'], 0)
        time_per_angle = self.compute_frame_time()
        collection_time = self.num_angles * time_per_angle
        self.wait_camera_done(collection_time + 60.)


    def program_PSO(self):
        '''Performs programming of PSO output on the Aerotech driver.
        '''
        overall_sense, user_direction = self._compute_senses()
        asynRec = self.epics_pvs['PSOAsyn']
        pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
        pso_input = int(self.epics_pvs['PSOEncoderInput'].get(as_string=True))

        #Place the motor at the position where the first PSO pulse should be triggered
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)
        self.epics_pvs['Rotation'].put(self.rotation_start, wait=True)
        self.epics_pvs['RotationSpeed'].put(self.motor_speed)

        #Make sure the PSO control is off
        asynRec.put('PSOCONTROL %s RESET' % pso_axis, wait=True, timeout=10.0)
        time.sleep(0.05)
        #Set the output to occur from the I/O terminal on the controller
        asynRec.put('PSOOUTPUT %s CONTROL 1' % pso_axis, wait=True, timeout=10.0)
        time.sleep(0.05)
        #Set a pulse 10 us long, 20 us total duration, so 10 us on, 10 us off
        asynRec.put('PSOPULSE %s TIME 20,10' % pso_axis, wait=True, timeout=10.0)
        time.sleep(0.05)
        #Set the pulses to only occur in a specific window
        asynRec.put('PSOOUTPUT %s PULSE WINDOW MASK' % pso_axis, wait=True, timeout=10.0)
        time.sleep(0.05)
        #Set which encoder we will use.  3 = the MXH (encoder multiplier) input, which is what we generally want
        asynRec.put('PSOTRACK %s INPUT %d' % (pso_axis, pso_input), wait=True, timeout=10.0)
        time.sleep(0.05)
        #Set the distance between pulses.  Do this in encoder counts.
        asynRec.put('PSODISTANCE %s FIXED %d' % (pso_axis,
                             self.epics_pvs['EncoderPulsesPerStep'].get()), wait=True, timeout=10.0)
        time.sleep(0.05)
        #Which encoder is being used to calculate whether we are in the window.  1 for single axis
        asynRec.put('PSOWINDOW %s 1 INPUT %d' % (pso_axis, pso_input), wait=True, timeout=10.0)
        time.sleep(0.05)

        #Calculate window function parameters.  Must be in encoder counts, and is 
        #referenced from the stage location where we arm the PSO.  We are at that point now.
        #We want pulses to start at start - delta/2, end at end + delta/2.  
        range_start = -round(self.epics_pvs['EncoderPulsesPerStep'].get()/ 2) * overall_sense
        range_length = self.epics_pvs['EncoderPulsesPerStep'].get() * self.num_angles
        #The start of the PSO window must be < end.  Handle this.
        if overall_sense > 0:
            window_start = range_start
            window_end = window_start + range_length
        else:
            window_end = range_start
            window_start = window_end - range_length
        asynRec.put('PSOWINDOW %s 1 RANGE %d,%d' % (pso_axis, window_start-5, window_end+5), wait=True, timeout=10.0)
        #Arm the PSO
        time.sleep(0.05)
        asynRec.put('PSOCONTROL %s ARM' % pso_axis, wait=True, timeout=10.0)


    def cleanup_PSO(self):
        '''Cleanup activities after a PSO scan. 
        Turns off PSO and sets the speed back to default.
        '''
        log.info('Cleaning up PSO programming and setting to retrace speed.')
        asynRec = self.epics_pvs['PSOAsyn']
        pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
        pso_input = self.epics_pvs['PSOEncoderInput'].get(as_string=True)
        asynRec.put('PSOWINDOW %s OFF' % pso_axis, wait=True)
        asynRec.put('PSOCONTROL %s OFF' % pso_axis, wait=True)


    def _compute_senses(self):
        '''Computes whether this motion will be increasing or decreasing encoder counts.
        
        user direction, overall sense.
        '''
        # Encoder direction compared to dial coordinates.  Hard code this; could ask controller
        encoder_dir = -1
        #Get motor direction (dial vs. user); convert (0,1) = (pos, neg) to (1, -1)
        motor_dir = 1 - int(self.epics_pvs['RotationDirection'].get()) * 2
        #Figure out whether motion is in positive or negative direction in user coordinates
        user_direction = 1 if self.rotation_stop > self.rotation_start else -1
        #Figure out overall sense: +1 if motion in + encoder direction, -1 otherwise
        return user_direction * motor_dir * encoder_dir, user_direction

        
    def compute_positions(self):
        '''Computes several parameters describing the fly scan motion.
        Computes the spacing between points, ensuring it is an integer number
        of encoder pulses.
        Uses this spacing to recalculate the end of the scan, if necessary.
        Computes the taxi distance at the beginning and end of scan to allow
        the stage to accelerate to speed.
        '''
        overall_sense, user_direction = self._compute_senses()
        #Get the distance needed for acceleration = 1/2 a t^2 = 1/2 * v * t
        motor_accl_time = float(self.epics_pvs['RotationAccelTime'].get())    #Acceleration time in s
        accel_dist = motor_accl_time / 2.0 * float(self.motor_speed) 

        #Compute the actual delta to keep each interval an integer number of encoder counts
        encoder_multiply = float(self.epics_pvs['PSOPulsesPerRotation'].get()) / 360.
        raw_delta_encoder_counts = self.rotation_step * encoder_multiply
        delta_encoder_counts = round(raw_delta_encoder_counts)
        if abs(raw_delta_encoder_counts - delta_encoder_counts) > 1e-4:
            log.warning('  *** *** *** Requested scan would have used a non-integer number of encoder pulses.')
            log.warning('  *** *** *** Calculated # of encoder pulses per step = {0:9.4f}'.format(raw_delta_encoder_counts))
            log.warning('  *** *** *** Instead, using {0:d}'.format(delta_encoder_counts))
        self.epics_pvs['EncoderPulsesPerStep'].put(delta_encoder_counts)
        #Change the rotation step Python variable and PV
        self.rotation_step = delta_encoder_counts / encoder_multiply
        self.epics_pvs['RotationStep'].put(self.rotation_step)
                  
        #Make taxi distance an integer number of measurement deltas >= accel distance
        #Add 1/2 of a delta to ensure that we are really up to speed.
        taxi_dist = (math.ceil(accel_dist / self.rotation_step) + 0.5) * self.rotation_step 
        self.epics_pvs['startTaxi'].put(self.rotation_start - taxi_dist * user_direction)
        self.epics_pvs['endTaxi'].put(self.rotation_stop + taxi_dist * user_direction)
        
        #Where will the last point actually be?
        self.rotation_stop = (self.rotation_start 
                                + (self.num_angles - 1) * self.rotation_step * user_direction)
