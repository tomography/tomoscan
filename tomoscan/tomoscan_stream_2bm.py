"""
.. _tomoStream: https://tomostream.readthedocs.io
.. _circular buffer plugin: https://cars9.uchicago.edu/software/epics/NDPluginCircularBuff.html
.. _AreaDetector: https://areadetector.github.io/master/index.html
.. _stream: https://tomoscan.readthedocs.io/en/latest/tomoScanApp.html#tomoscan-2bm-stream-adl

Software for tomography stream scanning with EPICS at APS beamline 2-BM

This class support `tomoStream`_ by providing:

- Dark-flat field image PVs broadcasting
    | Dark-flat field images are broadcasted using PVaccess. Dark-flat field images are also saved in a temporary \
    hdf5 file that are re-written whenever new flat/dark fields are acquired. Acquisition of dark and flat fields is \
    performed without stopping rotation of the stage. Dark-flat field images can also be binned setting the binning \
    parameter in ROI1 plugin.
- On-demand capturing to an hdf5 file
    | The capturing/saving to an hdf5 file can be done on-demand by pressing the Capture proj button in the `Stream`_\
    MEDM control screen. Whenever capturing is done, dark/flat fields from the temporarily hdf5 file are added to the file containing \
    the projections and the experimental meta data. In addition, the `circular buffer plugin`_ (CB1) of `AreaDetector`_ \
    is used to store a set of projections acquired before capturing is started. This allows to save projections containing \
    information about the sample right before a sample change is detected. Data from the circular buffer is also added to \
    the hdf5 after capturing is done. The resulting hdf5 file has the same format as in regular single tomoscan file. 


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
import pvaccess

EPSILON = .001

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
        
        # Set data directory
        file_path = self.epics_pvs['DetectorTopDir'].get(as_string=True) + self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + os.path.sep + self.epics_pvs['UserLastName'].get(as_string=True) + os.path.sep
        self.epics_pvs['FilePath'].put(file_path, wait=True)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Set standard file template on file writer
        self.epics_pvs['FPFileTemplate'].put("%s%s_%3.3d.h5", wait=True)

        # Disable overw writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')
        
        self.stream_init()

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
    
    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Calls the base class method.

        - Opens the front-end shutter.
        
        - Sets the PSO controller.

        - Creates theta array using list from PSO. 

        """
        log.info('begin scan')
        # Call the base class method
        super().begin_scan()
        # Opens the front-end shutter
        self.open_frontend_shutter()
         
        # Confirm angle step is an integer number of encoder pulses
        # Pass the user selected values to the PSO
        self.epics_pvs['PSOstartPos'].put(self.rotation_start, wait=True)
        self.wait_pv(self.epics_pvs['PSOstartPos'], self.rotation_start)
        self.epics_pvs['PSOendPos'].put(self.rotation_stop, wait=True)
        self.wait_pv(self.epics_pvs['PSOendPos'], self.rotation_stop)
        # Compute and set the motor speed
        time_per_angle = self.compute_frame_time()+7.2/1000
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

        # Create theta array
        self.theta = []
        self.theta = self.epics_pvs['ThetaArray'].get(count=int(self.num_angles))       

        self.begin_stream()     
        
    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.

        - Closes shutter.
        """
        log.info('tomoscan_stream_2bm: end scan')
        log.info('end scan')
        
        self.end_stream()

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
        time_per_angle = self.compute_frame_time()+7.2/1000
        collection_time = self.num_angles * time_per_angle
        
        self.wait_camera_done(collection_time + 60.)

    def abort_scan(self):
        """Performs the operations needed when a scan is aborted.

        This does the following:

        - Calls the base class method.
        """

        log.info('Stream abort')
        
        # Call the base class method        
        super().abort_scan()
                


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
        
        self.pv_dark = pvaccess.PvObject({'value': [pvaccess.pvaccess.ScalarType.FLOAT], 
            'sizex': pvaccess.pvaccess.ScalarType.INT, 
            'sizey': pvaccess.pvaccess.ScalarType.INT})
        self.server_dark = pvaccess.PvaServer('2bma:TomoScan:StreamDarkFields', self.pv_dark)

        self.pv_flat = pvaccess.PvObject({'value': [pvaccess.pvaccess.ScalarType.FLOAT], 
            'sizex': pvaccess.pvaccess.ScalarType.INT, 
            'sizey': pvaccess.pvaccess.ScalarType.INT})
        self.server_flat = pvaccess.PvaServer('2bma:TomoScan:StreamFlatFields', self.pv_flat)
    

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
            self.epics_pvs['StreamBinning'].put(int(numpy.log2(self.epics_pvs['ROIBinX'].get())))  
    
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
        hdf_file = util.open_hdf5(file_name,'r+')                
        unique_ids = hdf_file['/defaults/NDArrayUniqueId'][:]
        theta = self.epics_pvs['ThetaArray'].get(count=int(self.epics_pvs['NumAngles'].get()))             
        dset = hdf_file.create_dataset('/exchange/theta', (len(unique_ids),), dtype='float32')
        dset[:] = theta[unique_ids]        
        log.info('theta to save: %s .. %s', theta[unique_ids[0]], theta[unique_ids[-1]])
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
        h5file = util.open_hdf5(dirname+'/dark_fields.h5','r')
        data = h5file['exchange/data_dark'][:]
        data = numpy.mean(data.astype('float32'),0)
        for k in range(self.epics_pvs['StreamBinning'].get() ):
            data = 0.5*(data[:, ::2]+data[:, 1::2])
            data = 0.5*(data[::2, :]+data[1::2, :])
        self.pv_dark['value'] = data.flatten()
        self.pv_dark['sizex'] = data.shape[1] 
        self.pv_dark['sizey'] = data.shape[0]          
        
    def broadcast_flat(self):
        """Broadcast flat fields
        
        - read flat fields from the file
        - take average and bin flat fields according to StreamBinning parameter
        - broadcast flat field with the pv variable    
        """
        
        log.info('broadcast flat fields')        
        dirname = os.path.dirname(self.epics_pvs['FPFullFileName'].get(as_string=True))            
        h5file = util.open_hdf5(dirname+'/flat_fields.h5','r') 
        data = h5file['exchange/data_white'][:]
        data = numpy.mean(data.astype('float32'),0)
        for k in range(self.epics_pvs['StreamBinning'].get() ):
            data = 0.5*(data[:, ::2]+data[:, 1::2])
            data = 0.5*(data[::2, :]+data[1::2, :])
        self.pv_flat['value'] = data.flatten()
        self.pv_flat['sizex'] = data.shape[1] 
        self.pv_flat['sizey'] = data.shape[0]          
        
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
