"""Software for tomography scanning with EPICS at APS beamline 2-BM-A

   Classes
   -------
   TomoScan2BM
     Derived class for tomography scanning with EPICS at APS beamline 2-BM-A
"""
import os
import time
import h5py 
import numpy

from tomoscan import TomoScan
from tomoscan import log
from tomoscan import util
import threading
import numpy as np

EPSILON = .001
TESTING = True

class TomoScanStream2BM(TomoScan):
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
        # Set the detector in idle
        self.set_trigger_mode('Internal', 1)

        # This is used by the streaming reconstruction to stop the analysis
        self.epics_pvs['StreamStatus'].put('Off')
        
        # Set data directory
        file_path = self.epics_pvs['DetectorTopDir'].get(as_string=True) + self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + os.path.sep + self.epics_pvs['UserLastName'].get(as_string=True) + os.path.sep
        self.epics_pvs['FilePath'].put(file_path, wait=True)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Set standard file template on file writer
        self.epics_pvs['FPFileTemplate'].put("%s%s_%3.3d.h5", wait=True)

        # Disable overw writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

        # Unset retake button
        self.epics_pvs['StreamRetakeFlat'].put(0)

        
        # Initialize plugins pvs
        self.epics_pvs['PVANDArrayPort'].put('ROI1')
        self.epics_pvs['ROINDArrayPort'].put('SP1')
        self.epics_pvs['CBNDArrayPort'].put('SP1')
        self.epics_pvs['FPNDArrayPort'].put('SP1')

        self.epics_pvs['PVAEnableCallbacks'].put('Enable')
        self.epics_pvs['ROIEnableCallbacks'].put('Enable')
        self.epics_pvs['CBEnableCallbacks'].put('Enable')
        self.epics_pvs['FPEnableCallbacks'].put('Enable')
                
        self.epics_pvs['ROIScale'].put(4) # should be binx*biny   
        self.epics_pvs['ROIBinX'].put(2) # 2 should be a parameter in the tomoscan medm   
        self.epics_pvs['ROIBinY'].put(2) # 2 should be a parameter in the tomoscan medm   

        self.capturing = 0 # flag for controling only one capturing
        
        self.epics_pvs['FPCaptureRBV'].add_callback(self.pv_callback_stream)
        self.epics_pvs['StreamRetakeFlat'].add_callback(self.pv_callback_stream)
        self.epics_pvs['StreamPreCount'].add_callback(self.pv_callback_stream)
        
        

    def open_frontend_shutter(self):
        """Opens the shutters to collect flat fields or projections.

        This does the following:

        - Opens the 2-BM-A front-end shutter.

        """

        # Open 2-BM-A front-end shutter
        if not self.epics_pvs['OpenShutter'] is None:
            pv = self.epics_pvs['OpenShutter']
            value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
            status = self.epics_pvs['ShutterStatus'].get(as_string=True)
            log.info('shutter status: %s', status)
            log.info('open shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenShutter'].put(value, wait=True)
            self.wait_pv(self.epics_pvs['ShutterStatus'], 1)
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

        - Opens the front-end shutter

        - Turns on StreamStatus.
        
        - Sets the PSO controller.

        - Creates theta array using list from PSO. 

        - Turns on streaming for dark/flat capture.
        """
        log.info('begin scan')
        # Call the base class method
        super().begin_scan()
        # Opens the front-end shutter
        if not TESTING:
            self.open_frontend_shutter()
 
        # This marks the beginning of the streaming mode
        self.epics_pvs['StreamStatus'].put('On')

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

        # # set dark/flat to be taken at beginning
        self.epics_pvs['FlatFieldMode'].put('None', wait=True)
        self.epics_pvs['DarkFieldMode'].put('None', wait=True)
        
        # self.file_name = self.epics_pvs['FPFileName'].get(as_string=True)
        # self.file_template = self.epics_pvs['FPFileTemplate'].get(as_string=True)
        # self.autoincrement = self.epics_pvs['FPAutoIncrement'].get(as_string=True)
        
        # self.epics_pvs['FPFileName'].put('dark_flat_buffer.h5', wait=True)
        # self.epics_pvs['FPFileTemplate'].put('%s%s', wait=True)
        # self.epics_pvs['FPAutoIncrement'].put("No", wait=True)

        # # Compute total number of frames to capture (dark+flat)
        # self.total_images = self.num_dark_fields+self.num_flat_fields        
        # # Set the total number of frames to capture and start capture on file plugin
        # self.epics_pvs['FPNumCapture'].put(self.total_images, wait=True)
        # self.epics_pvs['FPCapture'].put('Capture')
        

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Turns off streaming.

        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.

        - Closes shutter.
        """
        log.info('tomoscan_stream_2bm: end scan')
        log.info('end scan')
        # This is used by the streaming reconstruction to stop the analysis
        self.epics_pvs['StreamStatus'].put('Off')

        # Put the camera back in FreeRun mode and acquiring
        self.set_trigger_mode('FreeRun', 1)
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

        - Restore file name for on demand projection capturing.

        - Set the rotation motor position specified by the ``RotationStart`` PV in the
          PSOstartPos.

        - Computes and sets the speed of the rotation motor so that it reaches the next projection
          angle just after the current exposure and readout are complete.

        - These will be used by the PSO to calculate the Taxi distance and rotary stage acceleration.

        - Starts the PSOfly.

        - Wait on the PSO done.
        """
        

        log.info('collect projections')
        super().collect_projections()
        # # restore file name 
        # self.epics_pvs['FPFileName'].put(self.file_name, wait=True)                        
        # self.epics_pvs['FPFileTemplate'].put(self.file_template, wait=True)                        
        # self.epics_pvs['FPAutoIncrement'].put(self.autoincrement, wait=True)                        
        
        
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


        # start writing to the circular buffer
        self.change_cbsize()
        
        self.wait_camera_done(collection_time + 60.)

    def abort_scan(self):
        """Aborts a scan that is running.
        Calls abort() and sets the StreamStatus to 'Off'
        """

        log.info('abort')
        # Stop the rotary stage
        self.epics_pvs['RotationStop'].put(1)
        self.wait_pv(self.epics_pvs['RotationDmov'], 0)

        super().abort_scan()
                
        self.epics_pvs['StreamStatus'].put('Off')

    def pv_callback_stream(self, pvname=None, value=None, char_value=None, **kw):
        """Callback functions for the streaming mode"""

        if ((pvname.find('Capture_RBV') != -1) and (value == 1) and (self.capturing==0)
            and (self.epics_pvs['FrameType'].get(as_string=True)=='Projection')):
            thread = threading.Thread(target=self.capture_projections, args=())
            thread.start()            
        if (pvname.find('StreamRetakeFlat') != -1) and (value == 1):
            thread = threading.Thread(target=self.retake_dark_flat, args=())
            thread.start() 
        if (pvname.find('StreamPreCount') != -1):
            thread = threading.Thread(target=self.change_cbsize, args=())
            thread.start() 
          
    def capture_projections(self):
        """Monitor the capturing projections process: capture projections, save pre-buffer, 
        dump angles, copy dark and flat fields. The result of this capturing process is 3 files, e.g.
        scan_045.h5 (captured projections), cb_scan_045.h5 (pre-buffer with projections), 
        df_scan_045.h5 (dark flat fields).

        """
        #1) set capturing flag to 1
        #2) disable CB1 plugin
        #3) wait when captruing is finished
        #4) dump angles
        #5) save file name
        #6) switch input port of hdf5 plugin to CB1
        #7) change hdf5 file name to cb_*file_name*
        #8) set the number of captured as the cb size, press capture
        #9) press trigger button in CB1
        #10) enable CB1 callbacks
        #11) wait when trigger is finished
        #12) start CB1 capturing again
        #13) dump angles to cb        
        #14) copy dark_flat fields file to the one having the same index as data
        #15) change hdf5 file name back to the initial one            
        #16) switch input port for hdf plugin to SP1        
        #17) set capturing flag to 0

        log.info('capture projections')
        self.capturing = 1
        
        self.epics_pvs['CBEnableCallbacks'].put('Disable')        
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)
        self.dump_theta(self.epics_pvs['FPFullFileName'].get(as_string=True))
        
        if(self.epics_pvs['StreamPreCount'].get()>0):
            log.info('save pre-buffer')
            file_name = self.epics_pvs['FPFileName'].get(as_string=True)
            file_template = self.epics_pvs['FPFileTemplate'].get(as_string=True)
            autoincrement =  self.epics_pvs['FPAutoIncrement'].get(as_string=True)
            basename = os.path.basename(self.epics_pvs['FPFullFileName'].get(as_string=True))
            dirname = os.path.dirname(self.epics_pvs['FPFullFileName'].get(as_string=True))
            
            self.epics_pvs['FPFileName'].put('cb_'+ basename, wait=True)
            self.epics_pvs['FPFileTemplate'].put('%s%s', wait=True)
            self.epics_pvs['FPAutoIncrement'].put('No', wait=True)                                
            self.epics_pvs['FPNDArrayPort'].put('CB1')                

            self.epics_pvs['FPNumCapture'].put(self.epics_pvs['StreamPreCount'].get(), wait=True)
            self.epics_pvs['FPCapture'].put('Capture')
            self.epics_pvs['CBTrigger'].put('Trigger')      
            self.wait_pv(self.epics_pvs['FPCaptureRBV'], 1)            
            self.wait_pv(self.epics_pvs['CBTriggerRBV'], 1)                    
            self.epics_pvs['CBEnableCallbacks'].put('Enable')     
            self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)            
            self.epics_pvs['CBCapture'].put('Capture')   
            self.dump_theta(self.epics_pvs['FPFullFileName'].get(as_string=True))
        
        log.info('save dark flat fields')
        cmd = 'cp '+ dirname+'/df.h5 '+ dirname + '/df_'+ basename
        os.popen(cmd)
        
        self.epics_pvs['FPFileName'].put(file_name, wait=True)
        self.epics_pvs['FPFileTemplate'].put(file_template, wait=True)        
        self.epics_pvs['FPAutoIncrement'].put(autoincrement, wait=True)                        
        self.epics_pvs['FPNDArrayPort'].put('SP1')                        

        self.capturing = 0
        
    def retake_dark_flat(self):
        """Recollect dark and flat fields while in the streaming mode"""

        #1) set capturing flag to 1
        #2) turn off streaming    
        #3) save file_name    
        #4) change file name to df.h5
        #5) collect flat fields
        #7) return file name to the initial one 
        #8) set the frame type to 'Projection'
        #9) set the retake flat button to Off
        #10) set stream status to On
        #11) set capturing flag to 0
        log.info('retake dark and flat')
        self.capture = 1

        self.epics_pvs['StreamStatus'].put('Off')        
        file_name = self.epics_pvs['FPFileName'].get(as_string=True)
        file_template = self.epics_pvs['FPFileTemplate'].get(as_string=True)
        autoincrement =  self.epics_pvs['FPAutoIncrement'].get(as_string=True)

        self.epics_pvs['FPFileName'].put('df.h5', wait=True)        
        self.epics_pvs['FPFileTemplate'].put('%s%s', wait=True)
        self.epics_pvs['FPAutoIncrement'].put('No', wait=True)                                

        super().collect_flat_fields()        
        self.epics_pvs['FPNumCapture'].put(self.num_flat_fields, wait=True)        
        self.epics_pvs['FPCapture'].put('Capture', wait=True)   
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)                                
        #self.close_shutter()
        super().collect_dark_fields()        
        self.epics_pvs['FPNumCapture'].put(self.num_dark_fields, wait=True)        
        self.epics_pvs['FPCapture'].put('Capture', wait=True)   
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)                                
        self.open_shutter()
        
        self.move_sample_in()
                
        self.epics_pvs['FPFileName'].put(self.epics_pvs['FPFileName'].get(as_string=True)[3:], wait=True)                        
        self.epics_pvs['ScanStatus'].put('Collecting projections', wait=True)
        self.epics_pvs['FrameType'].put('Projection', wait=True)
        self.epics_pvs['StreamRetakeFlat'].put(0)   
        self.epics_pvs['StreamStatus'].put('On')

        self.epics_pvs['FPFileName'].put(file_name, wait=True)
        self.epics_pvs['FPFileTemplate'].put(file_template, wait=True)        
        self.epics_pvs['FPAutoIncrement'].put(autoincrement, wait=True) 
        
        self.capture = 0

    def change_cbsize(self):
        """ Change pre-buffer size"""        
        #1) set precount in CB to the new size
        #2) set postcount in CB to the new size
        #3) stop CB capturing
        #4) start CB capturing
        
        log.info('change pre-buffer size')

        newsize = self.epics_pvs['StreamPreCount'].get()
        self.epics_pvs['CBPreCount'].put(newsize, wait=True)
        self.epics_pvs['CBPostCount'].put(newsize, wait=True)
        self.epics_pvs['CBCapture'].put('Done')
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)                    
        self.epics_pvs['CBCapture'].put('Capture')


    def dump_theta(self, file_name):
        """Add theta to the hdf5 file by using unique ids stored in the same hdf5 file
        """ 

        #1) read unique projection ids from the hdf5 file
        #2) take angles y ids from the PSO
        #3) dump angles into hdf5 file
        log.info('dump theta into the hdf5 file',file_name)

        hdf_file = util.open_hdf5(file_name,'r+')                
        unique_ids = hdf_file['/defaults/NDArrayUniqueId'][:]
        theta = self.epics_pvs['ThetaArray'].get(count=int(self.epics_pvs['NumAngles'].get()))             
        dset = hdf_file.create_dataset('/exchange/theta', (len(unique_ids),), dtype='float32')
        dset[:] = theta[unique_ids]
        
        log.info('theta to save: %s', theta[unique_ids])
        log.info('total saved theta: %s', len(unique_ids))        