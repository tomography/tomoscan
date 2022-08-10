"""Software for tomography scanning with EPICS at APS beamline 2-BM

   Classes
   -------
   TomoScan2BM
     Derived class for tomography scanning with EPICS at APS beamline 2-BM
"""
import time
import os
import h5py 
import sys
import traceback
import numpy as np
import cv2
import json
import pathlib

import sys,os
import time
import re
import serial
import telnetlib
import http.client as httplib
import base64
import string
import threading

from epics import PV

from tomoscan import data_management as dm
from tomoscan.tomoscan_helical import TomoScanHelical
from tomoscan import log

EPSILON = .001

class TomoScan2BM(TomoScanHelical):
    """Derived class used for tomography scanning with EPICS at APS beamline 2-BM

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
        macro = 'DET=' + self.pv_prefixes['Camera'] + ',' + 'TS=' + self.epics_pvs['Testing'].__dict__['pvname'].replace('Testing', '', 1)
        self.control_pvs['CamNDAttributesMacros'].put(macro)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Set standard file template on file writer
        self.epics_pvs['FPFileTemplate'].put("%s%s_%3.3d.h5", wait=True)

        # Disable over writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

        log.setup_custom_logger("./tomoscan.log")

        # try to read username/password for pdu and webcam
        access_fname = os.path.join(str(pathlib.Path.home()), 'access.json')
        with open(access_fname, 'r') as fp:
            self.access_dic = json.load(fp)
        
        # Configure callbacks for mctoptics
        prefix = self.pv_prefixes['MctOptics']
        self.epics_pvs['CameraSelect'] = PV(prefix + 'CameraSelect')
        camera_select = self.epics_pvs['CameraSelect'].value
        if camera_select == None:
            log.error('mctOptics is down. Please start mctOptics first')
        else:
            self.epics_pvs['Camera0'] = PV(prefix + 'Camera0PVPrefix')
            self.epics_pvs['Camera1'] = PV(prefix + 'Camera1PVPrefix')
            self.epics_pvs['CameraSelect'].add_callback(self.pv_callback_2bm)

    def pv_callback_2bm(self, pvname=None, value=None, char_value=None, **kw):
        """Callback function that is called by pyEpics when certain EPICS PVs are changed
        
        """
        log.debug('pv_callback_2bm pvName=%s, value=%s, char_value=%s', pvname, value, char_value)
        if (pvname.find('CameraSelect') != -1):
            thread = threading.Thread(target=self.reinit_camera, args=())
            thread.start()

    def reinit_camera(self):
        """Init camera PVs based on the mctOptics selection.

        Parameters
        ----------
       camera : int, optional
            The camera to use. Optique Peter system support 2 cameras
        """

        if not self.scan_is_running:
            camera_select = self.epics_pvs['CameraSelect'].value
            if camera_select == 0:
                 prefix = self.epics_pvs['Camera0'].get(as_string=True)
            else:
                 prefix = self.epics_pvs['Camera1'].get(as_string=True)

            camera_prefix = prefix + 'cam1:'
            self.control_pvs['CamManufacturer']        = PV(camera_prefix + 'Manufacturer_RBV')
            self.control_pvs['CamModel']               = PV(camera_prefix + 'Model_RBV')
            self.control_pvs['CamAcquire']             = PV(camera_prefix + 'Acquire')
            self.control_pvs['CamAcquireBusy']         = PV(camera_prefix + 'AcquireBusy')
            self.control_pvs['CamImageMode']           = PV(camera_prefix + 'ImageMode')
            self.control_pvs['CamTriggerMode']         = PV(camera_prefix + 'TriggerMode')
            self.control_pvs['CamNumImages']           = PV(camera_prefix + 'NumImages')
            self.control_pvs['CamNumImagesCounter']    = PV(camera_prefix + 'NumImagesCounter_RBV')
            self.control_pvs['CamAcquireTime']         = PV(camera_prefix + 'AcquireTime')
            self.control_pvs['CamAcquireTimeRBV']      = PV(camera_prefix + 'AcquireTime_RBV')
            self.control_pvs['CamBinX']                = PV(camera_prefix + 'BinX')
            self.control_pvs['CamBinY']                = PV(camera_prefix + 'BinY')
            self.control_pvs['CamWaitForPlugins']      = PV(camera_prefix + 'WaitForPlugins')
            self.control_pvs['PortNameRBV']            = PV(camera_prefix + 'PortName_RBV')
            self.control_pvs['CamNDAttributesFile']    = PV(camera_prefix + 'NDAttributesFile')
            self.control_pvs['CamNDAttributesMacros']  = PV(camera_prefix + 'NDAttributesMacros')

            # If this is a Point Grey camera then assume we are running ADSpinnaker
            # and create some PVs specific to that driver
            manufacturer = self.control_pvs['CamManufacturer'].get(as_string=True)
            model = self.control_pvs['CamModel'].get(as_string=True)
            if (manufacturer.find('Point Grey') != -1) or (manufacturer.find('FLIR') != -1):
                self.control_pvs['CamExposureMode']     = PV(camera_prefix + 'ExposureMode')
                self.control_pvs['CamTriggerOverlap']   = PV(camera_prefix + 'TriggerOverlap')
                self.control_pvs['CamPixelFormat']      = PV(camera_prefix + 'PixelFormat')
                self.control_pvs['CamArrayCallbacks']   = PV(camera_prefix + 'ArrayCallbacks')
                self.control_pvs['CamFrameRateEnable']  = PV(camera_prefix + 'FrameRateEnable')
                self.control_pvs['CamTriggerSource']    = PV(camera_prefix + 'TriggerSource')
                self.control_pvs['CamTriggerSoftware']  = PV(camera_prefix + 'TriggerSoftware')
                if model.find('Grasshopper3 GS3-U3-23S6M') != -1:
                    self.control_pvs['CamVideoMode']    = PV(camera_prefix + 'GC_VideoMode_RBV')
                if model.find('Blackfly S BFS-PGE-161S7M') != -1:
                    self.control_pvs['GC_ExposureAuto'] = PV(camera_prefix + 'GC_ExposureAuto')       

    def open_frontend_shutter(self):
        """Opens the shutters to collect flat fields or projections.

        This does the following:

        - Checks if we are in testing mode. If we are, do nothing else opens the 2-BM front-end shutter.

        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
        else:
            # Open 2-BM front-end shutter
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

        - Opens the 2-BM fast shutter.
        """

        # Open 2-BM fast shutter
        if not self.epics_pvs['OpenFastShutter'] is None:
            pv = self.epics_pvs['OpenFastShutter']
            value = self.epics_pvs['OpenFastShutterValue'].get(as_string=True)
            log.info('open fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenFastShutter'].put(value, wait=True)
            log.warning("Wait 2s  - Temporarily while there is no fast shutter at 2bmb ")
            time.sleep(2)

    def close_frontend_shutter(self):
        """Closes the shutters to collect dark fields.
        This does the following:

        - Closes the 2-BM front-end shutter.

        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
        else:
            # Close 2-BM front-end shutter
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

        - Closes the 2-BM fast shutter.
        """

        # Close 2-BM fast shutter
        if not self.epics_pvs['CloseFastShutter'] is None:
            pv = self.epics_pvs['CloseFastShutter']
            value = self.epics_pvs['CloseFastShutterValue'].get(as_string=True)
            log.info('close fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseFastShutter'].put(value, wait=True)
            log.warning("Wait 2s  - Temporarily while there is no fast shutter at 2bmb ")
            time.sleep(2)

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
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        if(camera_model=='Oryx ORX-10G-51S5M' or camera_model=='Oryx ORX-10G-310S9M'):            
            self.set_trigger_mode_oryx(trigger_mode, num_images)
        elif(camera_model=='Grasshopper3 GS3-U3-23S6M'):        
            self.set_trigger_mode_grasshopper(trigger_mode, num_images)
        elif(camera_model=='Q-12A180-Fm/CXP-6'):          
            self.set_trigger_mode_adimec(trigger_mode, num_images)
        else:
            log.error('Camera is not supported')
            exit(1)

    def set_trigger_mode_oryx(self, trigger_mode, num_images):
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
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)   # VN: For FLIR we first switch to Off and then change overlap. any reason of that?                                                 
            self.epics_pvs['CamTriggerSource'].put('Line2', wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple')            
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateEnable'].put(0)

            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 1)
 
    def set_trigger_mode_grasshopper(self, trigger_mode, num_images):
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
   
    def set_trigger_mode_adimec(self, trigger_mode, num_images):
        self.epics_pvs['CamAcquire'].put('Done') ###
        self.wait_pv(self.epics_pvs['CamAcquire'], 0) ###
        log.info('set trigger mode: %s', trigger_mode)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.wait_pv(self.epics_pvs['CamExposureMode'], 0)                
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.wait_pv(self.epics_pvs['CamExposureMode'], 0)
            self.epics_pvs['CamImageMode'].put('Multiple')            
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else: # set camera to external triggering
            self.epics_pvs['CamExposureMode'].put('TimedTriggerCont', wait=True)                
            self.wait_pv(self.epics_pvs['CamExposureMode'], 3)                
            self.epics_pvs['CamImageMode'].put('Multiple')                        
            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)            

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Set data directory.

        - Set the TomoScan xml files

        - Calls the base class method.
        
        - Opens the front-end shutter.

        - Sets the PSO controller.

        - Creates theta array using list from PSO. 

        - Turns on data capture.
        """
        log.info('begin scan')

        # Set data directory
        file_path = self.epics_pvs['DetectorTopDir'].get(as_string=True) + self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + os.path.sep + self.epics_pvs['UserLastName'].get(as_string=True) + os.path.sep
        self.epics_pvs['FilePath'].put(file_path, wait=True)

        # NetBooter = NetBooter_Control(mode='telnet',id=self.access_dic['pdu_username'],password=self.access_dic['pdu_password'],ip=self.access_dic['pdu_ip_address'])           
        # NetBooter.power_off(1)
        
        # Call the base class method
        super().begin_scan()
        # Opens the front-end shutter
        self.open_frontend_shutter()

        
    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Calls ``save_configuration()``.

        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.

        - Closes shutter.  

        - Add theta to the raw data file. 

        - Copy raw data to data analysis computer.      
        """

        if self.return_rotation == 'Yes':
            # Reset rotation position by mod 360 , the actual return 
            # to start position is handled by super().end_scan()
             # allow stage to stop
            log.info('wait until the stage is stopped')
            time.sleep(self.epics_pvs['RotationAccelTime'].get()*1.2)                        
            ang = self.epics_pvs['RotationRBV'].get()
            current_angle = np.sign(ang)*(np.abs(ang)%360)
            self.epics_pvs['RotationSet'].put('Set', wait=True)
            self.epics_pvs['Rotation'].put(current_angle, wait=True)
            self.epics_pvs['RotationSet'].put('Use', wait=True)
        # Close shutter
        self.close_shutter()

        # Stop the file plugin
        self.epics_pvs['FPCapture'].put('Done')
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)
        # Add theta in the hdf file
        self.add_theta()

        log.info('Adding a frame from the IP camera')
        ret, frame = cv2.VideoCapture('http://remotecam02bmb:Cam-02-bm-b@164.54.113.162/cgi-bin/mjpeg?stream=1').read()# we should hide the password

        #station A        
        # NetBooter = NetBooter_Control(mode='telnet',id=self.access_dic['pdu_username'],password=self.access_dic['pdu_password'],ip=self.access_dic['pdu_ip_address'])
        # NetBooter.power_on(1)
        # log.info('wait 10 sec while the web camera has focused')
        # time.sleep(10)                       
        # ret, frame = cv2.VideoCapture('http://remotecam02bma:Cam-02-bm-a@164.54.113.137/cgi-bin/mjpeg?stream=1').read()# we should hide the password
        #ret, frame = cv2.VideoCapture('http://' + self.access_dic['webcam_username'] +':' + self.access_dic['webcam_password'] + '@' + self.access_dic['webcam_ip_address'] + '/cgi-bin/mjpeg?stream=1').read()
        # NetBooter.power_off(1)                       
        

        if ret==True:
            full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
            with h5py.File(full_file_name,'r+') as fid:
                fid.create_dataset('exchange/web_camera_frame', data=frame)
            log.info('The frame was added')
        else:
            log.warning('The frame was not added')
        
        # Copy raw data to data analysis computer    
        if self.epics_pvs['CopyToAnalysisDir'].get():
            log.info('Automatic data trasfer to data analysis computer is enabled.')
            full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
            remote_analysis_dir = self.epics_pvs['RemoteAnalysisDir'].get(as_string=True)
            dm.scp(full_file_name, remote_analysis_dir)
        else:
            log.warning('Automatic data trasfer to data analysis computer is disabled.')
        
        # Call the base class method
        super().end_scan()
        
    def set_scan_exposure_time(self, exposure_time=None):

        camera_model = self.epics_pvs['CamModel'].get(as_string=True)        
        if(camera_model=='Q-12A180-Fm/CXP-6'):
            if exposure_time is None:
                exposure_time = self.epics_pvs['ExposureTime'].value            
            self.epics_pvs['CamAcquisitionFrameRate'].put(1/exposure_time, wait=True, timeout=10.0) 
            self.epics_pvs['CamAcquireTime'].put(exposure_time, wait=True, timeout = 10.0)
        else:
            super().set_scan_exposure_time(exposure_time)

    def add_theta(self):
        """Add theta at the end of a scan.
        """
        log.info('add theta')

        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        if os.path.exists(full_file_name):
            try:                
                with h5py.File(full_file_name, "a") as f:
                    if self.theta is not None:                        
                        unique_ids = f['/defaults/NDArrayUniqueId']
                        hdf_location = f['/defaults/HDF5FrameLocation']
                        total_dark_fields = self.num_dark_fields * ((self.dark_field_mode in ('Start', 'Both')) + (self.dark_field_mode in ('End', 'Both')))
                        total_flat_fields = self.num_flat_fields * ((self.flat_field_mode in ('Start', 'Both')) + (self.flat_field_mode in ('End', 'Both')))                        
                        
                        proj_ids = unique_ids[hdf_location[:] == b'/exchange/data']
                        flat_ids = unique_ids[hdf_location[:] == b'/exchange/data_white']
                        dark_ids = unique_ids[hdf_location[:] == b'/exchange/data_dark']

                        # create theta dataset in hdf5 file
                        if len(proj_ids) > 0:
                            theta_ds = f.create_dataset('/exchange/theta', (len(proj_ids),))
                            theta_ds[:] = self.theta[proj_ids - proj_ids[0]]

                        # warnings that data is missing
                        if len(proj_ids) != len(self.theta):
                            log.warning(f'There are {len(self.theta) - len(proj_ids)} missing data frames')
                            missed_ids = [ele for ele in range(len(self.theta)) if ele not in proj_ids-proj_ids[0]]
                            missed_theta = self.theta[missed_ids]
                            # log.warning(f'Missed ids: {list(missed_ids)}')
                            log.warning(f'Missed theta: {list(missed_theta)}')
                        if len(flat_ids) != total_flat_fields:
                            log.warning(f'There are {total_flat_fields - len(flat_ids)} missing flat field frames')
                        if (len(dark_ids) != total_dark_fields):
                            log.warning(f'There are {total_dark_fields - len(dark_ids)} missing dark field frames')
            except:
                log.error('Add theta: Failed accessing: %s', full_file_name)
                traceback.print_exc(file=sys.stdout)

        else:
            log.error('Failed adding theta. %s file does not exist', full_file_name)

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

class NetBooter_Control:
    '''
    Offer NetBooter Control class:
        Support serial/telnet/http control
        Support outlet status checker / power on / power off / reboot
        Power on/off return setting success or fail, but reboot no return

    How to use it:

    From Serial
    NetBooter = NetBooter_Control(mode='serial',serial_port='COM1')
    NetBooter.power_on(1)                              #Return (True,'') for set Outlet 1 ON success
    NetBooter.power_off(5)                             #Return (True,'') for set Outlet 5 OFF success
    NetBooter.reboot(3)                                #No return, use NetBooter internal reboot function, don't suggest to use it
    Outlet3_Status = NetBooter.check_outlet_status(3)  #Return (True,'') for Outlet 3 is ON | (False,'') for OFF

    From HTTP
    NetBooter = NetBooter_Control(mode='http',ip='192.168.1.101')
    NetBooter.power_on(2)                              #Return (True,'') for set Outlet 2 ON success
    NetBooter.power_off(4)                             #Return (True,'') for set Outlet 4 OFF success
    Outlet3_Status = NetBooter.check_outlet_status(3)  #Return (True,'') for Outlet 3 is ON | (False,'') for OFF

    '''
    def __init__(self,mode='serial',serial_port='COM1',id='admin',password='admin',ip='0.0.0.0'):
        '''
        Class init
        Input: mode(serial/telnet/http)
               id/password [for login NetBooter]
               For serial: serial_port([Windows]COM1/COM2/COM3/[Linux]/dev/tty...)
               For telnet/http: ip
        '''
        if not isinstance(mode,str):     raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid mode '+str(mode))
        if not isinstance(id,str):       raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid id '+str(id))
        if not isinstance(password,str): raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid password '+str(password))
        self.mode = mode.lower()
        self.id = id
        self.password = password
        if self.mode == 'serial':
            self.NetBooter_serial = serial.Serial()
            self.NetBooter_serial.port = serial_port
            self.NetBooter_serial.baudrate = 9600
            self.NetBooter_serial.timeout = 3
            self.NetBooter_serial.bytesize = serial.EIGHTBITS
            self.NetBooter_serial.parity = serial.PARITY_NONE
            self.NetBooter_serial.stopbits = serial.STOPBITS_ONE
            self.NetBooter_serial.xonxoff = 0
            try:
                self.NetBooter_serial.open()
            except Exception as e:
                raise Exception(str(e))
            if not self.NetBooter_serial.isOpen():
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Fail to open '+str(serial_port))
            for outlet in xrange(1,6):
                self.power_on(outlet)
        elif self.mode == 'telnet':
            self.ip = ip
            self.NetBooter_telnet = telnetlib.Telnet(self.ip)
        elif self.mode == 'http':
            self.ip = ip
            self.auth = base64.b64encode(bytearray(('%s:%s' % (self.id, self.password)).replace('\n', ''), 'utf-8'))
            self.NetBooter_httpconnection = httplib.HTTPConnection(self.ip,timeout=10)
        self.__check_netbooter__()

    def __check_netbooter__(self):
        if self.mode == 'serial':
            try:
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write('\nsysshow\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                temp1 = self.NetBooter_serial.read(300)
                self.NetBooter_serial.write('\nsysshow\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                temp2 = self.NetBooter_serial.read(300)
                status = temp1+temp2
                self.NetBooter_serial.flushOutput()
            except Exception as e:
                raise Exception(str(e))
            if status.find('System Name') == -1:
                raise Exception('Invalid NetBooter')
        elif self.mode == 'telnet':
            pass
        elif self.mode == 'http':
            NetBooter_Pattern = re.compile(r'Synaccess.*?NetBooter',re.I)
            NetBooter_rly_Pattern = re.compile(r'<a onclick="ajxCmd\(\'(.*?rly.*?)\d\'\);">')
            NetBooter_rb_Pattern  = re.compile(r'<a onclick="ajxCmd\(\'(.*?rb.*?)\d\'\);">')
            try:
                self.NetBooter_httpconnection.putrequest("POST",'')
                self.NetBooter_httpconnection.putheader("Authorization", "Basic %s" % self.auth)
                self.NetBooter_httpconnection.endheaders()
                response = self.NetBooter_httpconnection.getresponse()
                res = response.read()
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Init http connection to NetBooter fail: '+str(e))
            if response.status != 200:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Init http connection to NetBooter fail: '+str(response.status))
            if not NetBooter_Pattern.search(res):
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] http connection is not NetBooter: '+str(res))
            rly_pair = NetBooter_rly_Pattern.search(res)
            if rly_pair:
                self.rly_url = rly_pair.group(1)
            else:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Fail to find NetBooter rly url: '+str(res))
            rb_pair = NetBooter_rb_Pattern.search(res)
            if rb_pair:
                self.rb_url = rb_pair.group(1)
            else:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Fail to find NetBooter rb url: '+str(res))

    def __del__(self):
        if self.mode == 'serial':
            self.NetBooter_serial.close()
        elif self.mode == 'telnet':
            self.NetBooter_telnet.close()
        elif self.mode == 'http':
            self.NetBooter_httpconnection.close()

    def check_outlet_status(self,outlet):
        '''
        Check outlet status
        Input: outlet(1/2/3/4/5)
        Output: True,''(For ON)/False,''(For OFF)/Exception,Exception Reason
        '''
        if outlet not in (1,2,3,4,5,'1','2','3','4','5'):
            raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid NetBooter outlet: '+str(outlet))
        outlet = int(outlet)
        if self.mode == 'serial':
            if not self.NetBooter_serial.readable() or not self.NetBooter_serial.writable():
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] NetBooter Serial not Readable/Writeable')
            try:
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write('\nsysshow\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                temp1 = self.NetBooter_serial.read(300)
                self.NetBooter_serial.write('\nsysshow\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                temp2 = self.NetBooter_serial.read(300)
                status = temp1+temp2
                self.NetBooter_serial.flushOutput()
            except Exception as e:
                raise Exception(str(e))
            try:
                for line in status.split('\n'):
                    if line.find('Outlet Status(1-On, 0-Off. Outlet 1 to 5):') > -1:
                        #Clean Unrecognizable Code
                        line = line[43:].replace('\x00','')
                        #Outlet list should be ['','0/1','0/1','0/1','0/1','0/1','']
                        outlets = line.split(' ')
                        if outlets[outlet] == '0':
                            return False,''
                        elif outlets[outlet] == '1':
                            return True,''
                        else:
                            raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid Status: '+str(outlets))
            except Exception as e:
                return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e)
            return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Not find outlet: '+str(status)
        elif self.mode == 'telnet':
            try:
                self.NetBooter_telnet.write('\r\nsysshow\r\n'.encode('ascii'))
                temp = self.NetBooter_telnet.read_until(b'Note - use WEB access for more settings',2)
            except Exception as e:
                raise Exception(str(e))
            try:
                for line in status.split('\n'):
                    if line.find('Outlet Status(1-On, 0-Off. Outlet 1 to 5):') > -1:
                        #Clean Unrecognizable Code
                        line = line[43:].replace('\x00','')
                        #Outlet list should be ['','0/1','0/1','0/1','0/1','0/1','']
                        outlets = line.split(' ')
                        if outlets[outlet] == '0':
                            return False,''
                        elif outlets[outlet] == '1':
                            return True,''
                        else:
                            raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid Status: '+str(outlets))
            except Exception as e:
                return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e)
            return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Not find outlet: '+str(status)
        elif self.mode == 'http':
            res = self.NetBooter_httppost(url="/status.xml")
            if res[0] != True:
                return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] No proper response from NetBooter: '+res[1]
            swoutlet = outlet - 1
            pattern = re.compile(r'<rly%s>(1|0)</rly%s>'%(swoutlet,swoutlet))
            if not pattern.search(res[1]):
                return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Not find proper outlet status: '+res[1]
            status = pattern.search(res[1]).group()[6:7]
            if status == '0':
                return False,''
            elif status == '1':
                return True,''
            else:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid Status: '+str(status))

    def login(self):
        '''
        Login NetBooter for serial/telnet mode
        No output
        '''
        if self.mode == 'serial':
            if not self.NetBooter_serial.writable():
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] NetBooter Serial not Writeable')
            try:
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write('\n!\nlogin\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write(str(self.id)+'\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write(str(self.password)+'\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))
        elif self.mode == 'telnet':
            try:
                self.NetBooter_telnet.write('\r\nlogin\r\n'.encode('ascii'))
                self.NetBooter_telnet.write((str(self.id)+'\r\n').encode('ascii'))
                self.NetBooter_telnet.write((str(self.password)+'\r\n').encode('ascii'))
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))

    def power_on(self,outlet):
        '''
        Set specific outlet on
        Input: outlet(1/2/3/4/5)
        Output: True,''[Set success]/False,''[Set fail]/Exception,''
        '''
        if outlet not in (1,2,3,4,5,'1','2','3','4','5'):
            raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid NetBooter outlet: '+str(outlet))
        outlet = int(outlet)

        if self.mode == 'http':
            current_status = self.check_outlet_status(outlet)
            if current_status[0] == True:
                return True,''
            elif current_status[0] == False:
                swoutlet = outlet - 1
                url = "/%s%s"%(self.rly_url,swoutlet)
                res = self.NetBooter_httppost(url)
                if res[0] == True:
                    if res[1] == 'Success! ':
                        new_status = self.check_outlet_status(outlet)
                        if new_status[0] == True:
                            return True,''
                        elif new_status[0] == False:
                            return False,'['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Power on outlet fail2: '+new_status[1]
                        else:
                            return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+new_status[1]
                    else:
                        return False,'['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Power on outlet fail1: '+res[1]
                else:
                    return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+res[1]
            else:
                return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+current_status[1]
            time.sleep(2)

        self.login()
        if self.mode == 'serial':
            if not self.NetBooter_serial.writable():
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] NetBooter Serial not Writeable')
            try:
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write('\npset '+str(outlet)+' 1\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                time.sleep(1)
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))

        elif self.mode == 'telnet':
            try:
                self.NetBooter_telnet.write(('\r\npset '+str(outlet)+' 1\r\n').encode('ascii'))
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))

        res_on = self.check_outlet_status(outlet)
        if res_on[0] == True:
            return True,''
        elif res_on[0] == False:
            return False,''
        else:
            return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+res_on[1]

    def power_off(self,outlet):
        '''
        Set specific outlet off
        Input: outlet(1/2/3/4/5)
        Output: True,''[Set success]/False,''[Set fail]/Exception,''
        '''
        if outlet not in (1,2,3,4,5,'1','2','3','4','5'):
            raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid NetBooter outlet: '+str(outlet))
        outlet = int(outlet)

        if self.mode == 'http':
            current_status = self.check_outlet_status(outlet)
            if current_status[0] == False:
                return True,''
            elif current_status[0] == True:
                swoutlet = outlet - 1
                url = "/%s%s"%(self.rly_url,swoutlet)
                res = self.NetBooter_httppost(url)
                if res[0] == True:
                    if res[1] == 'Success! ':
                        new_status = self.check_outlet_status(outlet)
                        if new_status[0] == False:
                            return True,''
                        elif new_status[0] == True:
                            return False,'['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Power off outlet fail2: '+new_status[1]
                        else:
                            return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+new_status[1]
                    else:
                        return False,'['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Power off outlet fail1: '+res[1]
                else:
                    return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+res[1]
            else:
                return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+current_status[1]
            time.sleep(2)

        self.login()
        if self.mode == 'serial':
            if not self.NetBooter_serial.writable():
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] NetBooter Serial not Writeable')
            try:
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write('\npset '+str(outlet)+' 0\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                time.sleep(1)
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))

        elif self.mode == 'telnet':
            try:
                self.NetBooter_telnet.write(('\r\npset '+str(outlet)+' 0\r\n').encode('ascii'))
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))

        res_off = self.check_outlet_status(outlet)
        if res_off[0] == False:
            return True,''
        elif res_off[0] == True:
            return False,''
        else:
            return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+res_off[1]

    def reboot(self,outlet):
        '''
        Set specific outlet reboot by internal reboot function from NetBooter
        Input: outlet(1/2/3/4/5)
        No output
        '''
        if outlet not in (1,2,3,4,5,'1','2','3','4','5'):
            raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Invalid NetBooter outlet: '+str(outlet))
        outlet = int(outlet)

        if self.mode == 'http':
            current_status = self.check_outlet_status(outlet)
            swoutlet = outlet - 1
            url = "/%s%s"%(self.rb_url,swoutlet)
            res = self.NetBooter_httppost(url)
            time.sleep(3)
            if res[0] == True:
                if res[1] == 'Success! ':
                    new_status = self.check_outlet_status(outlet)

        self.login()
        if self.mode == 'serial':
            if not self.NetBooter_serial.writable():
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] NetBooter Serial not Writeable')

            try:
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                self.NetBooter_serial.write('\nrb '+str(outlet)+'\n')
                self.NetBooter_serial.flush()
                self.NetBooter_serial.flushInput()
                self.NetBooter_serial.flushOutput()
                #time.sleep(1)
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))
        elif self.mode == 'telnet':
            try:
                self.NetBooter_telnet.write(('\r\nrb '+str(outlet)+'\r\n').encode('ascii'))
            except Exception as e:
                raise Exception('['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e))

    def NetBooter_httppost(self,url):
        '''
        Common NetBooter http post
        Input: url(/status.xml[for get stauts] or /cmd.cgi?rly=#1[for set power on/off])
        '''
        try:
            self.NetBooter_httpconnection.putrequest("POST", url)
            self.NetBooter_httpconnection.putheader("Authorization", "Basic %s" % self.auth)
            self.NetBooter_httpconnection.endheaders()
            response = self.NetBooter_httpconnection.getresponse()
            res = response.read()
        except Exception as e:
            return 'Exception','['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+']'+str(e)
        if response.status != 200:
            return False,'['+os.path.basename(__file__)+']['+sys._getframe().f_code.co_name+'] Unknown http connection status: '+str(response.status)
        return True,res
