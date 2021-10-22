"""Software for tomography scanning with EPICS

   Classes
   -------
   TomoScanPSO
     Derived class for tomography scanning with EPICS using Aerotech controllers and PSO trigger outputs
"""

import time
import os
import math
import numpy as np
import pvaccess
import threading
from tomoscan import util
from tomoscan import TomoScan
from tomoscan import log

class TomoScanStreamPSO(TomoScan):
    """Derived class used for tomography scanning with EPICS using Aerotech controllers and PSO trigger outputs

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

        # On the A3200 we can read the number of encoder counts per rotation from the controller
        # Unfortunately the Ensemble does not support this
        pso_model = self.epics_pvs['PSOControllerModel'].get(as_string=True)
        if (pso_model == 'A3200'):
            pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
            self.epics_pvs['PSOCommand.BOUT'].put("UNITSTOCOUNTS(%s, 360.0)" % pso_axis, wait=True, timeout=10.0)
            reply = self.epics_pvs['PSOCommand.BINP'].get(as_string=True)
            counts_per_rotation = float(reply[1:])
            self.epics_pvs['PSOCountsPerRotation'].put(counts_per_rotation)
        

        # Setting the pva servers to broadcast dark and flat fields
        if 'PvaStream' in self.pv_prefixes:
            prefix = self.pv_prefixes['PvaStream']
            
            self.pva_stream_dark = pvaccess.PvObject({'value': [pvaccess.pvaccess.ScalarType.FLOAT], 
                'sizex': pvaccess.pvaccess.ScalarType.INT, 
                'sizey': pvaccess.pvaccess.ScalarType.INT})
            self.pva_server_dark = pvaccess.PvaServer(prefix + 'StreamDarkFields', self.pva_stream_dark)
            self.pva_stream_flat = pvaccess.PvObject({'value': [pvaccess.pvaccess.ScalarType.FLOAT], 
                'sizex': pvaccess.pvaccess.ScalarType.INT, 
                'sizey': pvaccess.pvaccess.ScalarType.INT})
            self.pva_server_flat = pvaccess.PvaServer(prefix + 'StreamFlatFields', self.pva_stream_flat)

            self.pva_stream_theta = pvaccess.PvObject({'value': [pvaccess.pvaccess.ScalarType.DOUBLE], 
                'sizex': pvaccess.pvaccess.ScalarType.INT})
            self.pva_server_theta = pvaccess.PvaServer(prefix + 'StreamTheta', self.pva_stream_theta)
                                    
        self.stream_init()


    def collect_dark_fields(self):
        """Collects dark field images.
        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumDarkFields`` PV.
        """

        log.info('collect dark fields')
        super().collect_dark_fields()


    def collect_flat_fields(self):
        """Collects flat field images.
        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumFlatFields`` PV.
        """
        log.info('collect flat fields')
        super().collect_flat_fields()

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
        time_per_angle = self.compute_frame_time()+7.2/1000 # temporary fix for 2-BM-B
        self.motor_speed = self.rotation_step / time_per_angle
        time.sleep(0.1)

        # Program the stage driver to provide PSO pulses
        self.compute_positions_PSO()

        self.program_PSO()

        self.begin_stream()  

        
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
        self.end_stream()
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
        # Need to wait a short time for AcquireBusy to change to 1
        time.sleep(0.5)
        log.info('start fly scan')

        # Start fly scan
        self.epics_pvs['Rotation'].put(self.epics_pvs['PSOEndTaxi'].get())
        time_per_angle = self.compute_frame_time()
        collection_time = self.num_angles * time_per_angle
        self.wait_camera_done(collection_time + 60.)

    def program_PSO(self):
        '''Performs programming of PSO output on the Aerotech driver.
        '''
        overall_sense, user_direction = self._compute_senses()
        pso_command = self.epics_pvs['PSOCommand.BOUT']
        pso_model = self.epics_pvs['PSOControllerModel'].get(as_string=True)
        pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
        pso_input = int(self.epics_pvs['PSOEncoderInput'].get(as_string=True))

        # Place the motor at the position where the first PSO pulse should be triggered
        self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)
        self.epics_pvs['Rotation'].put(self.rotation_start, wait=True)
        self.epics_pvs['RotationSpeed'].put(self.motor_speed)

        # Make sure the PSO control is off
        pso_command.put('PSOCONTROL %s RESET' % pso_axis, wait=True, timeout=10.0)
        # Set the output to occur from the I/O terminal on the controller
        if (pso_model == 'Ensemble'):
            pso_command.put('PSOOUTPUT %s CONTROL 1' % pso_axis, wait=True, timeout=10.0)
        elif (pso_model == 'A3200'):
            pso_command.put('PSOOUTPUT %s CONTROL 0 1' % pso_axis, wait=True, timeout=10.0)
        # Set the pulse width.  The total width and active width are the same, since this is a single pulse.
        pulse_width = self.epics_pvs['PSOPulseWidth'].get()
        pso_command.put('PSOPULSE %s TIME %f,%f' % (pso_axis, pulse_width, pulse_width), wait=True, timeout=10.0)
        # Set the pulses to only occur in a specific window
        pso_command.put('PSOOUTPUT %s PULSE WINDOW MASK' % pso_axis, wait=True, timeout=10.0)
        # Set which encoder we will use.  3 = the MXH (encoder multiplier) input, which is what we generally want
        pso_command.put('PSOTRACK %s INPUT %d' % (pso_axis, pso_input), wait=True, timeout=10.0)
        # Set the distance between pulses. Do this in encoder counts.
        pso_command.put('PSODISTANCE %s FIXED %d' % (pso_axis, 
                        self.epics_pvs['PSOEncoderCountsPerStep'].get()) , wait=True, timeout=10.0)
        # Which encoder is being used to calculate whether we are in the window.  1 for single axis
        pso_command.put('PSOWINDOW %s 1 INPUT %d' % (pso_axis, pso_input), wait=True, timeout=10.0)

        # Calculate window function parameters.  Must be in encoder counts, and is 
        # referenced from the stage location where we arm the PSO.  We are at that point now.
        # We want pulses to start at start - delta/2, end at end + delta/2.  
        range_start = -round(self.epics_pvs['PSOEncoderCountsPerStep'].get()/ 2) * overall_sense
        range_length = self.epics_pvs['PSOEncoderCountsPerStep'].get() * self.num_angles
        # The start of the PSO window must be < end.  Handle this.
        if overall_sense > 0:
            window_start = range_start
            window_end = window_start + range_length
        else:
            window_end = range_start
            window_start = window_end - range_length
        pso_command.put('PSOWINDOW %s 1 RANGE %d,%d' % (pso_axis, window_start-5, window_end+5), wait=True, timeout=10.0)
        # Arm the PSO
        pso_command.put('PSOCONTROL %s ARM' % pso_axis, wait=True, timeout=10.0)

    def cleanup_PSO(self):
        '''Cleanup activities after a PSO scan. 
        Turns off PSO and sets the speed back to default.
        '''
        log.info('Cleaning up PSO programming.')
        pso_model = self.epics_pvs['PSOControllerModel'].get(as_string=True)
        pso_command = self.epics_pvs['PSOCommand.BOUT']
        pso_axis = self.epics_pvs['PSOAxisName'].get(as_string=True)
        if (pso_model == 'Ensemble'):
            pso_command.put('PSOWINDOW %s OFF' % pso_axis, wait=True)
        elif (pso_model == 'A3200'):
            pso_command.put('PSOWINDOW %s 1 OFF' % pso_axis, wait=True)
        pso_command.put('PSOCONTROL %s OFF' % pso_axis, wait=True)

    def _compute_senses(self):
        '''Computes whether this motion will be increasing or decreasing encoder counts.
        
        user direction, overall sense.
        '''
        # Encoder direction compared to dial coordinates
        encoder_dir = 1 if self.epics_pvs['PSOEncoderCountsPerStep'].get() > 0 else -1
        # Get motor direction (dial vs. user); convert (0,1) = (pos, neg) to (1, -1)
        motor_dir = 1 if self.epics_pvs['RotationDirection'].get() == 0 else -1
        # Figure out whether motion is in positive or negative direction in user coordinates
        user_direction = 1 if self.rotation_stop > self.rotation_start else -1
        # Figure out overall sense: +1 if motion in + encoder direction, -1 otherwise
        return user_direction * motor_dir * encoder_dir, user_direction
        
    def compute_positions_PSO(self):
        '''Computes several parameters describing the fly scan motion.
        Computes the spacing between points, ensuring it is an integer number
        of encoder counts.
        Uses this spacing to recalculate the end of the scan, if necessary.
        Computes the taxi distance at the beginning and end of scan to allow
        the stage to accelerate to speed.
        Assign the fly scan angular position to theta[]
        '''
        overall_sense, user_direction = self._compute_senses()
        # Get the distance needed for acceleration = 1/2 a t^2 = 1/2 * v * t
        motor_accl_time = float(self.epics_pvs['RotationAccelTime'].get()) # Acceleration time in s
        accel_dist = motor_accl_time / 2.0 * float(self.motor_speed) 

        # Compute the actual delta to keep each interval an integer number of encoder counts
        encoder_multiply = float(self.epics_pvs['PSOCountsPerRotation'].get()) / 360.
        raw_delta_encoder_counts = self.rotation_step * encoder_multiply
        delta_encoder_counts = round(raw_delta_encoder_counts)
        if abs(raw_delta_encoder_counts - delta_encoder_counts) > 1e-4:
            log.warning('  *** *** *** Requested scan would have used a non-integer number of encoder counts.')
            log.warning('  *** *** *** Calculated # of encoder counts per step = {0:9.4f}'.format(raw_delta_encoder_counts))
            log.warning('  *** *** *** Instead, using {0:d}'.format(delta_encoder_counts))
        self.epics_pvs['PSOEncoderCountsPerStep'].put(delta_encoder_counts)
        # Change the rotation step Python variable and PV
        self.rotation_step = delta_encoder_counts / encoder_multiply
        self.epics_pvs['RotationStep'].put(self.rotation_step)
          
        # Make taxi distance an integer number of measurement deltas >= accel distance
        # Add 1/2 of a delta to ensure that we are really up to speed.
        taxi_dist = (math.ceil(accel_dist / self.rotation_step) + 0.5) * self.rotation_step 
        self.epics_pvs['PSOStartTaxi'].put(self.rotation_start - taxi_dist * user_direction)
        self.epics_pvs['PSOEndTaxi'].put(self.rotation_stop + taxi_dist * user_direction)
        
        #Where will the last point actually be?
        self.rotation_stop = (self.rotation_start 
                                + (self.num_angles - 1) * self.rotation_step * user_direction)
        # Assign the fly scan angular position to theta[]
        self.theta = self.rotation_start + np.arange(self.num_angles) * self.rotation_step * user_direction
        self.pva_stream_theta['value'] = self.theta
        self.pva_stream_theta['sizex'] = self.num_angles





############################### STREAMING #####################################

    def stream_init(self):
        """Init streaming functionality
        
        - set plugins ports for streaming
        - enable callbacks in the ports
        - create pvaccess servers for dark and flat fields
        """

        port_name = self.epics_pvs['PortNameRBV'].get()
        self.epics_pvs['PVANDArrayPort'].put('ROI1')
        self.epics_pvs['ROINDArrayPort'].put(port_name)
        self.epics_pvs['CBNDArrayPort'].put(port_name)
        self.epics_pvs['FPNDArrayPort'].put(port_name)

        self.epics_pvs['PVAEnableCallbacks'].put('Enable')
        self.epics_pvs['ROIEnableCallbacks'].put('Enable')
        self.epics_pvs['CBEnableCallbacks'].put('Enable')
        self.epics_pvs['FPEnableCallbacks'].put('Enable')
        
    

    def begin_stream(self):
        """Streaming settings adjustments at the beginning of the scan

        - set dark/flat fields modes as None (do not take static dark/flat fields)
        - set binning in ROI1 plugin
        - set capturing status to Done for all capturing pvs
        - set circular buffer            
        - add callbacks for capturing pvs
        - add callbacks for changing sizes pvs          
        - add callbacks for syncing tomoscan pvs         
        
        - init flag for controling only one capturing at a time          
        """

        self.epics_pvs['FlatFieldMode'].put('None', wait=True)
        self.epics_pvs['DarkFieldMode'].put('None', wait=True)

        binning = self.epics_pvs['StreamBinning'].get()        
        self.epics_pvs['ROIBinX'].put(2**binning)    
        self.epics_pvs['ROIBinY'].put(2**binning)    
        self.epics_pvs['ROIScale'].put(2**(2*binning))
        
        self.epics_pvs['StreamCapture'].put('Done')
        self.epics_pvs['StreamRetakeDark'].put('Done')
        self.epics_pvs['StreamRetakeFlat'].put('Done')                
        
        self.change_cbsize()        
        
        self.epics_pvs['StreamCapture'].add_callback(self.pv_callback_stream_capture)
        self.epics_pvs['StreamRetakeDark'].add_callback(self.pv_callback_stream_capture)                
        self.epics_pvs['StreamRetakeFlat'].add_callback(self.pv_callback_stream_capture)
        self.epics_pvs['StreamPreCount'].add_callback(self.pv_callback_stream_change)
        self.epics_pvs['StreamBinning'].add_callback(self.pv_callback_stream_change)        
        self.epics_pvs['CBCurrentQtyRBV'].add_callback(self.pv_callback_stream_sync)        
        self.epics_pvs['CBStatusMessage'].add_callback(self.pv_callback_stream_sync)
        self.epics_pvs['FPNumCapture'].add_callback(self.pv_callback_stream_sync)
        self.epics_pvs['FPNumCaptured'].add_callback(self.pv_callback_stream_sync)
        
        self.capturing = 0              

    def end_stream(self):
        """Stream settings adjustments at the end of the scan

        - set capturing status to Done for all capturing pvs
        - remove callbacks 
        - set flag for controling only one capturing at a time to 0          
        """
        
        self.epics_pvs['StreamCapture'].put('Done')
        self.epics_pvs['StreamRetakeDark'].put('Done')
        self.epics_pvs['StreamRetakeFlat'].put('Done')        
                
        self.epics_pvs['StreamCapture'].remove_callback()
        self.epics_pvs['StreamRetakeDark'].remove_callback()                
        self.epics_pvs['StreamRetakeFlat'].remove_callback()
        self.epics_pvs['StreamPreCount'].remove_callback()
        self.epics_pvs['StreamBinning'].remove_callback()
        self.epics_pvs['CBCurrentQtyRBV'].remove_callback()
        self.epics_pvs['CBStatusMessage'].remove_callback()
        # self.epics_pvs['FPNumCaptureRBV'].remove_callback()        
        self.epics_pvs['FPNumCaptured'].remove_callback()
        
        self.capturing = 0  

    def pv_callback_stream_capture(self, pvname=None, value=None, char_value=None, **kw):
        """Callback functions for capturing in the streaming mode"""
                
        if(self.capturing==1):# if capturing is happening dont allow anything except the stop capturing callback
            if ((pvname.find('StreamCapture') != -1) and (value == 0)):
                thread = threading.Thread(target=self.stop_capture_projections, args=())
                thread.start()        
            # switch pv value to Done to be able to start capturing again
            self.epics_pvs[pvname[pvname.rfind(':')+1:]].put('Done')            
        else:
            if (pvname.find('StreamCapture') != -1) and (value == 1):
                thread = threading.Thread(target=self.capture_projections, args=())
                thread.start()            
            if (pvname.find('StreamRetakeDark') != -1) and (value == 1):
                thread = threading.Thread(target=self.retake_dark, args=())
                thread.start()                 
            if (pvname.find('StreamRetakeFlat') != -1) and (value == 1):
                thread = threading.Thread(target=self.retake_flat, args=())
                thread.start() 


    def pv_callback_stream_change(self, pvname=None, value=None, char_value=None, **kw):
        """Callback functions for changing parameters in the streaming mode"""      

        if(self.capturing==0): # dont allow to change during capturing       
            if (pvname.find('StreamPreCount') != -1):
                thread = threading.Thread(target=self.change_cbsize, args=())
                thread.start() 
            if (pvname.find('StreamBinning') != -1):
                thread = threading.Thread(target=self.change_binning, args=())
                thread.start() 
        else: # return to previous values
            self.epics_pvs['StreamPreCount'].put(self.epics_pvs['CBPreCount'].get())
            self.epics_pvs['StreamBinning'].put(int(np.log2(self.epics_pvs['ROIBinX'].get())))  
    
    def pv_callback_stream_sync(self, pvname=None, value=None, char_value=None, **kw):
        """Callback functions for syncing tomoscan pvs in the streaming mode"""      
        
        if (pvname.find('CurrentQty_RBV') != -1):
            thread = threading.Thread(target=self.change_cbqty, args=())
            thread.start() 
        if (pvname.find('StatusMessage') != -1):
            thread = threading.Thread(target=self.change_cbmessage, args=())
            thread.start() 
        # if (pvname.find('NumCapture') != -1):
        #     thread = threading.Thread(target=self.change_numcapture, args=())
        #     thread.start() 
        if (pvname.find('NumCaptured_RBV') != -1):
            thread = threading.Thread(target=self.change_numcaptured, args=())
            thread.start() 

    def capture_projections(self):
        """Monitor the capturing projections process: capture projections, save pre-buffer, 
        dump angles, copy dark and flat fields. The result of this capturing process is 4 files, e.g.
        scan_045.h5 (captured projections), circular_buffer_scan_045.h5 (pre-buffer with projections), 
        dark_fields_scan_045.h5 (dark fields), and flat_fields_scan_045.h5 (flat fields)

        - set capturing flag to 1
        - disable cb plugin
        - set number of captured frames in the hdf5 plugin as StreamNumCapture parameter
        - start capturing to the hdf5 file
        - wait when capturing is started
        - wait when captruing is finished
        - dump angles
        - take basename and dirname from full file name                          
        - copy dark_flat fields file to the one having the same index as data (eg. copy dark_fields.h5 dark_fields_scan_045.h5)
        - copy dark_flat fields file to the one having the same index as data (eg. copy flat_fields.h5 flat_fields_scan_045.h5)
          
        if circular buffer size > 0:
          - save file name
          - save hdf5 plugin port name
          - switch input port of hdf5 plugin to the circular buffer port
          - change hdf5 file name to circular_buffer_*file_name*
          - set the number of captured frames in the hdf5 as the currentQty value in cb
          - start capturing to the hdf5 file
          - set the number of post-count in cb plugin equal to currentQty 
          - press trigger button in cb plugin
          - enable cb callbacks
          - wait when trigger is finished
          - start cb capturing again
          - dump angles to hdf5 with data from cb        
          - switch input port for hdf plugin back to the initial                
          - change hdf5 file name back to the initial             
        
        - set capturing status to Done      
        - compute total number of captured frames and show it the medm screen
        - set capturing flag to 0
        
        """
        
        log.info('capture projections')
        self.epics_pvs['StreamMessage'].put('Capturing projections')

        self.capturing = 1
        self.epics_pvs['CBEnableCallbacks'].put('Disable')
        
        # set file name (extra check)
        file_name = self.epics_pvs['FileName'].get(as_string=True)        
        self.epics_pvs['FPFileName'].put(file_name,wait=True)                
        
        self.epics_pvs['FPNumCapture'].put(self.epics_pvs['StreamNumCapture'].get())
        self.epics_pvs['FPCapture'].put('Capture')
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 1)        
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)
        num_captured = self.epics_pvs['StreamNumCaptured'].get()

        self.dump_theta(self.epics_pvs['FPFullFileName'].get(as_string=True))
            
        basename = os.path.basename(self.epics_pvs['FPFullFileName'].get(as_string=True))
        dirname = os.path.dirname(self.epics_pvs['FPFullFileName'].get(as_string=True))                
        
        log.info('save dark fields')
        cmd = 'cp '+ dirname+'/dark_fields.h5 '+ dirname + '/dark_fields_'+ basename
        os.popen(cmd)
        log.info('save flat fields')        
        cmd = 'cp '+ dirname+'/flat_fields.h5 '+ dirname + '/flat_fields_'+ basename
        os.popen(cmd)
        
        if(self.epics_pvs['StreamPreCount'].get()>0):
            self.epics_pvs['StreamMessage'].put('Capturing circular buffer')                    
            log.info('save pre-buffer')        

            file_name = self.epics_pvs['FPFileName'].get(as_string=True)
            file_template = self.epics_pvs['FPFileTemplate'].get(as_string=True)
            autoincrement =  self.epics_pvs['FPAutoIncrement'].get(as_string=True)

            self.epics_pvs['FPFileName'].put('circular_buffer_'+ basename, wait=True)
            self.epics_pvs['FPFileTemplate'].put('%s%s', wait=True)
            self.epics_pvs['FPAutoIncrement'].put('No', wait=True)        
            fp_port_name = self.epics_pvs['FPNDArrayPort'].get(as_string=True)
            self.epics_pvs['FPNDArrayPort'].put(self.epics_pvs['CBPortNameRBV'].get())                

            self.epics_pvs['FPNumCapture'].put(self.epics_pvs['CBCurrentQtyRBV'].get(), wait=True)
            self.epics_pvs['FPCapture'].put('Capture')
            self.epics_pvs['CBPostCount'].put(self.epics_pvs['CBCurrentQtyRBV'].get(), wait=True)
            self.epics_pvs['CBTrigger'].put('Trigger')      
            self.wait_pv(self.epics_pvs['FPCaptureRBV'], 1)            
            self.wait_pv(self.epics_pvs['CBTriggerRBV'], 1)                    
            self.epics_pvs['CBEnableCallbacks'].put('Enable')     
            self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)            
            self.epics_pvs['CBCapture'].put('Capture')   
            self.dump_theta(self.epics_pvs['FPFullFileName'].get(as_string=True))
            self.epics_pvs['FPNDArrayPort'].put(fp_port_name)                        
            self.epics_pvs['FPFileName'].put(file_name, wait=True)
            self.epics_pvs['FPFileTemplate'].put(file_template, wait=True)        
            self.epics_pvs['FPAutoIncrement'].put(autoincrement, wait=True)                        
        
        num_captured += self.epics_pvs['StreamNumCaptured'].get()

        self.epics_pvs['StreamCapture'].put('Done')
        self.epics_pvs['StreamMessage'].put('Done')        
        self.epics_pvs['StreamFileName'].put(basename)
        self.epics_pvs['StreamNumTotalCaptured'].put(num_captured)
 
        #VN: Enable CB buffer again because if number of elements in CB==0 then the plugin will automatically turn off
        self.epics_pvs['CBEnableCallbacks'].put('Enable')
        self.capturing = 0
        

    def stop_capture_projections(self):  
        """Stop capturing projections"""  
        self.epics_pvs['FPCapture'].put('Done')


    def retake_dark(self):
        """Recollect dark  fields while in the streaming mode

        - set capturing flag to 1
        - save file_name    
        - change file name to dark_fields.h5
        - set frame type to DarkField
        - disable circular buffer plugin
        - close shutter
        - collect dark fields
        - enable circular buffer plugin        
        - return file name to the initial one 
        - set the frame type to 'Projection'
        - set the retake dark button to Done
        - broadcast dark fields   
        - set capturing flag to 0
        """
        
        log.info('retake dark')
        self.epics_pvs['StreamMessage'].put('Capturing dark fields')        
        self.capturing = 1

        file_name = self.epics_pvs['FPFileName'].get(as_string=True)
        file_template = self.epics_pvs['FPFileTemplate'].get(as_string=True)
        autoincrement =  self.epics_pvs['FPAutoIncrement'].get(as_string=True)

        self.epics_pvs['FPFileName'].put('dark_fields.h5', wait=True)        
        self.epics_pvs['FPFileTemplate'].put('%s%s', wait=True)
        self.epics_pvs['FPAutoIncrement'].put('No', wait=True)                                
        
        # switch frame type before closing the shutter to let the reconstruction engine 
        # know that following frames should not be used for reconstruction 
        self.epics_pvs['FrameType'].put('DarkField', wait=True)      
        
        self.epics_pvs['CBEnableCallbacks'].put('Disable')  

        super().collect_dark_fields()        
        self.epics_pvs['FPNumCapture'].put(self.num_dark_fields, wait=True)        
        self.epics_pvs['FPCapture'].put('Capture', wait=True)   
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)                                        

        self.open_shutter()

        self.epics_pvs['CBEnableCallbacks'].put('Enable')  

        self.epics_pvs['FPFileName'].put(file_name, wait=True)                        
        self.epics_pvs['ScanStatus'].put('Collecting projections', wait=True)

        self.epics_pvs['HDF5Location'].put(self.epics_pvs['HDF5ProjectionLocation'].value)
        self.epics_pvs['FrameType'].put('Projection', wait=True)
        self.epics_pvs['StreamRetakeDark'].put('Done')   
        
        self.epics_pvs['FPFileName'].put(file_name, wait=True)
        self.epics_pvs['FPFileTemplate'].put(file_template, wait=True)        
        self.epics_pvs['FPAutoIncrement'].put(autoincrement, wait=True) 
        
        self.broadcast_dark()
        self.epics_pvs['StreamMessage'].put('Done')        
        
        self.capturing = 0
 

    def retake_flat(self):
        """Recollect flat fields while in the streaming mode

        - set capturing flag to 1
        - save file_name    
        - change file name to flat_fields.h5
        - set frame type to FlatField
        - disable circular buffer plugin
        - collect flat fields
        - move sample in
        - set initial exposure time 
        - enable circular buffer plugin
        - return file name to the initial one 
        - set the frame type to 'Projection'
        - set the retake dark button to Done
        - broadcast flat fields   
        - set capturing flag to 0
        """
        
        log.info('retake flat')
        self.epics_pvs['StreamMessage'].put('Capturing flat fields')        
        
        self.capturing = 1

        file_name = self.epics_pvs['FPFileName'].get(as_string=True)
        file_template = self.epics_pvs['FPFileTemplate'].get(as_string=True)
        autoincrement =  self.epics_pvs['FPAutoIncrement'].get(as_string=True)

        self.epics_pvs['FPFileName'].put('flat_fields.h5', wait=True)        
        self.epics_pvs['FPFileTemplate'].put('%s%s', wait=True)
        self.epics_pvs['FPAutoIncrement'].put('No', wait=True)                                
        
        # switch frame type before closing the shutter to let the reconstruction engine 
        # know that following frames should not be used for reconstruction 
        self.epics_pvs['FrameType'].put('FlatField', wait=True)
        
        self.epics_pvs['CBEnableCallbacks'].put('Disable')  

        super().collect_flat_fields()        
        self.epics_pvs['FPNumCapture'].put(self.num_flat_fields, wait=True)        
        self.epics_pvs['FPCapture'].put('Capture', wait=True)   
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)      

        self.move_sample_in()
        self.set_exposure_time()
        
        self.epics_pvs['CBEnableCallbacks'].put('Enable')  
                
        self.epics_pvs['FPFileName'].put(file_name, wait=True)                        
        self.epics_pvs['ScanStatus'].put('Collecting projections', wait=True)
        self.epics_pvs['HDF5Location'].put(self.epics_pvs['HDF5ProjectionLocation'].value)        
        self.epics_pvs['FrameType'].put('Projection', wait=True)
        self.epics_pvs['StreamRetakeFlat'].put('Done')   
        
        self.epics_pvs['FPFileName'].put(file_name, wait=True)
        self.epics_pvs['FPFileTemplate'].put(file_template, wait=True)        
        self.epics_pvs['FPAutoIncrement'].put(autoincrement, wait=True) 
        
        self.broadcast_flat()
        self.epics_pvs['StreamMessage'].put('Done')                

        self.capturing = 0


    def change_cbsize(self):
        """ Change pre-buffer size        
        
        - set precount in circular buffer to the new size
        - stop cb capturing
        - start cb capturing
        """
        
        log.info('change pre-count size in the circular buffer')
        self.epics_pvs['CBCapture'].put('Done', wait=True)
        self.wait_pv(self.epics_pvs['CBCaptureRBV'], 0)                            
        self.epics_pvs['CBPreCount'].put(self.epics_pvs['StreamPreCount'].get(), wait=True)
        self.epics_pvs['CBCapture'].put('Capture')


    def dump_theta(self, file_name):
        """Add theta to the hdf5 file by using unique ids stored in the same hdf5 file

        - read unique projection ids from the hdf5 file
        - take angles by ids from the PSO
        - dump angles into hdf5 file
        """

        log.info('dump theta into the hdf5 file %s',file_name)
        with util.open_hdf5(file_name,'r+') as hdf_file:               
            unique_ids = hdf_file['/defaults/NDArrayUniqueId'][:]
            if '/exchange/theta' in hdf_file:
                del hdf_file['/exchange/theta']
            dset = hdf_file.create_dataset('/exchange/theta', (len(unique_ids),), dtype='float32')
            print(self.theta)
            print(len(self.theta))
            print(unique_ids)
            print(len(unique_ids))
            dset[:] = self.theta[unique_ids]        
        log.info('saved theta: %s .. %s', self.theta[unique_ids[0]], self.theta[unique_ids[-1]])
        log.info('total saved theta: %s', len(unique_ids))        


    def change_binning(self):
        """Change binning for broadcasted projections and dark/flat fields
        
        - change binning in the ROI1 plugin
        - broadcast binned dark and flat fields
        """

        log.info('change binning')
        binning = self.epics_pvs['StreamBinning'].get()        
        self.epics_pvs['ROIBinX'].put(2**binning)    
        self.epics_pvs['ROIBinY'].put(2**binning)    
        self.epics_pvs['ROIScale'].put(2**(2*binning))
        
        self.broadcast_dark()
        self.broadcast_flat()


    def broadcast_dark(self):
        """Broadcast dark fields

        - read dark fields from the file
        - take average and bin dark fields according to StreamBinning parameter
        - broadcast dark field with the pv variable    
        """

        log.info('broadcast dark fields')
        dirname = os.path.dirname(self.epics_pvs['FPFullFileName'].get(as_string=True))            
        with util.open_hdf5(dirname+'/dark_fields.h5','r') as h5file:
            data = h5file['exchange/data_dark'][:]
        data = np.mean(data.astype('float32'),0)
        for k in range(self.epics_pvs['StreamBinning'].get() ):
            data = 0.5*(data[:, ::2]+data[:, 1::2])
            data = 0.5*(data[::2, :]+data[1::2, :])
        self.pva_stream_dark['value'] = data.flatten()
        self.pva_stream_dark['sizex'] = data.shape[1] 
        self.pva_stream_dark['sizey'] = data.shape[0]          
        
    def broadcast_flat(self):
        """Broadcast flat fields
        
        - read flat fields from the file
        - take average and bin flat fields according to StreamBinning parameter
        - broadcast flat field with the pv variable    
        """
        
        log.info('broadcast flat fields')        
        dirname = os.path.dirname(self.epics_pvs['FPFullFileName'].get(as_string=True))            
        with util.open_hdf5(dirname+'/flat_fields.h5','r') as h5file:
            data = h5file['exchange/data_white'][:]
        data = np.mean(data.astype('float32'),0)
        for k in range(self.epics_pvs['StreamBinning'].get() ):
            data = 0.5*(data[:, ::2]+data[:, 1::2])
            data = 0.5*(data[::2, :]+data[1::2, :])
        self.pva_stream_flat['value'] = data.flatten()
        self.pva_stream_flat['sizex'] = data.shape[1] 
        self.pva_stream_flat['sizey'] = data.shape[0]          
        
    def change_cbqty(self):
        """Update current number of elements in the circular buffer """
        self.epics_pvs['StreamPreCounted'].put(self.epics_pvs['CBCurrentQtyRBV'].get())

    def change_cbmessage(self):
        """Update status message for the circular buffer """
        self.epics_pvs['StreamCBStatusMessage'].put(self.epics_pvs['CBStatusMessage'].get())

    # def change_numcapture(self):
    #     """Update number of frames to capture """
    #     self.epics_pvs['StreamNumCapture'].put(self.epics_pvs['FPNumCapture'].get())

    def change_numcaptured(self):
        """Update current number of captured frames """
        self.epics_pvs['StreamNumCaptured'].put(self.epics_pvs['FPNumCaptured'].get())
