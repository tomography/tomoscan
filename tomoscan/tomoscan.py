"""Software for tomography scanning with EPICS

   Classes
   -------
   TomoScan
     Base class for tomography scanning with EPICS.
"""

import json
import time
import threading
import signal
import sys
import os
from datetime import timedelta
import pymsgbox
from epics import PV
from tomoscan import log

class ScanAbortError(Exception):
    '''Exception raised when user wants to abort a scan.
    '''


class CameraTimeoutError(Exception):
    '''Exception raised when the camera times out during a scan.
    '''

class FileOverwriteError(Exception):
    '''Exception raised when a file would be overwritten.
    '''


class TomoScan():
    """ Base class used for tomography scanning with EPICS

    Parameters
    ----------
    pv_files : list of str
        List of files containing EPICS pvNames to be used.
    macros : dict
        Dictionary of macro definitions to be substituted when
        reading the pv_files
    """

    def __init__(self, pv_files, macros):
        self.scan_is_running = False
        self.config_pvs = {}
        self.control_pvs = {}
        self.pv_prefixes = {}

        # These variables are set in begin_scan().
        # They are used to prevent reading PVs repeatedly, and so that if the users changes
        # a PV during the scan it won't mess things up.
        self.exposure_time = None
        self.rotation_start = None
        self.rotation_step = None
        self.rotation_stop = None
        self.rotation_save = None
        self.rotation_resolution = None
        self.max_rotation_speed = None
        self.return_rotation = None
        self.num_angles = None
        self.num_dark_fields = None
        self.dark_field_mode = None
        self.num_flat_fields = None
        self.flat_field_mode = None
        self.total_images = None
        self.file_path_rbv = None
        self.file_name_rbv = None
        self.file_number = None
        self.file_template = None

        if not isinstance(pv_files, list):
            pv_files = [pv_files]
        for pv_file in pv_files:
            self.read_pv_file(pv_file, macros)

        if 'Rotation' not in self.control_pvs:
            log.error('RotationPVName must be present in autoSettingsFile')
            sys.exit()
        if 'Camera' not in self.pv_prefixes:
            log.error('CameraPVPrefix must be present in autoSettingsFile')
            sys.exit()
        if  'FilePlugin' not in self.pv_prefixes:
            log.error('FilePluginPVPrefix must be present in autoSettingsFile')
            sys.exit()

        #Define PVs we will need from the rotation motor, which is on another IOC
        rotation_pv_name = self.control_pvs['Rotation'].pvname
        self.control_pvs['RotationSpeed']          = PV(rotation_pv_name + '.VELO')
        self.control_pvs['RotationMaxSpeed']       = PV(rotation_pv_name + '.VMAX')
        self.control_pvs['RotationResolution']     = PV(rotation_pv_name + '.MRES')
        self.control_pvs['RotationEResolution']    = PV(rotation_pv_name + '.ERES')
        self.control_pvs['RotationSet']            = PV(rotation_pv_name + '.SET')
        self.control_pvs['RotationStop']           = PV(rotation_pv_name + '.STOP')
        self.control_pvs['RotationDmov']           = PV(rotation_pv_name + '.DMOV')
        self.control_pvs['RotationDirection']      = PV(rotation_pv_name + '.DIR')
        self.control_pvs['RotationAccelTime']      = PV(rotation_pv_name + '.ACCL')
        self.control_pvs['RotationRBV']            = PV(rotation_pv_name + '.RBV')
        self.control_pvs['RotationJog']            = PV(rotation_pv_name + '.JOGF')
        self.control_pvs['RotationSpeedJog']       = PV(rotation_pv_name + '.JVEL')
        self.control_pvs['RotationAccelJog']       = PV(rotation_pv_name + '.JAR')
        self.control_pvs['RotationOFF']            = PV(rotation_pv_name + '.OFF')

        #Define PVs from the camera IOC that we will need
        prefix = self.pv_prefixes['Camera']
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

        if (manufacturer.find('Adimec') != -1):
            self.control_pvs['CamExposureMode']            = PV(camera_prefix + 'ExposureMode')
            self.control_pvs['CamAcquisitionFrameRate']    = PV(camera_prefix + 'AcquisitionFrameRate')
            self.control_pvs['CamAcquisitionFramePeriod']  = PV(camera_prefix + 'AcquisitionFramePeriod')
            self.control_pvs['CamExposureTime+R']          = PV(camera_prefix + 'ExposureTime+R')
                         
        # Set some initial PV values
        self.control_pvs['CamWaitForPlugins'].put('Yes')
        self.control_pvs['StartScan'].put(0)
        
        prefix = self.pv_prefixes['FilePlugin']
        self.control_pvs['FPNDArrayPort']     = PV(prefix + 'NDArrayPort')        
        self.control_pvs['FPFileWriteMode']   = PV(prefix + 'FileWriteMode')
        self.control_pvs['FPNumCapture']      = PV(prefix + 'NumCapture')
        self.control_pvs['FPNumCaptured']     = PV(prefix + 'NumCaptured_RBV')
        self.control_pvs['FPCapture']         = PV(prefix + 'Capture')
        self.control_pvs['FPCaptureRBV']      = PV(prefix + 'Capture_RBV')
        self.control_pvs['FPFilePath']        = PV(prefix + 'FilePath')
        self.control_pvs['FPFilePathRBV']     = PV(prefix + 'FilePath_RBV')
        self.control_pvs['FPFilePathExists']  = PV(prefix + 'FilePathExists_RBV')
        self.control_pvs['FPFileName']        = PV(prefix + 'FileName')
        self.control_pvs['FPFileNameRBV']     = PV(prefix + 'FileName_RBV')
        self.control_pvs['FPFileNumber']      = PV(prefix + 'FileNumber')
        self.control_pvs['FPAutoIncrement']   = PV(prefix + 'AutoIncrement')
        self.control_pvs['FPFileTemplate']    = PV(prefix + 'FileTemplate')
        self.control_pvs['FPFullFileName']    = PV(prefix + 'FullFileName_RBV')
        self.control_pvs['FPAutoSave']        = PV(prefix + 'AutoSave')
        self.control_pvs['FPEnableCallbacks'] = PV(prefix + 'EnableCallbacks')
        self.control_pvs['FPXMLFileName']     = PV(prefix + 'XMLFileName')

        # Set some initial PV values
        file_path = self.config_pvs['FilePath'].get(as_string=True)
        self.control_pvs['FPFilePath'].put(file_path)
        file_name = self.config_pvs['FileName'].get(as_string=True)
        self.control_pvs['FPFileName'].put(file_name)
        self.control_pvs['FPAutoSave'].put('No')
        self.control_pvs['FPFileWriteMode'].put('Stream')
        self.control_pvs['FPEnableCallbacks'].put('Enable')

        #Define PVs from the MCS or PSO that live on another IOC
        if 'MCS' in self.pv_prefixes:
            prefix = self.pv_prefixes['MCS']
            self.control_pvs['MCSEraseStart']      = PV(prefix + 'EraseStart')
            self.control_pvs['MCSStopAll']         = PV(prefix + 'StopAll')
            self.control_pvs['MCSPrescale']        = PV(prefix + 'Prescale')
            self.control_pvs['MCSDwell']           = PV(prefix + 'Dwell')
            self.control_pvs['MCSLNEOutputWidth']  = PV(prefix + 'LNEOutputWidth')
            self.control_pvs['MCSChannelAdvance']  = PV(prefix + 'ChannelAdvance')
            self.control_pvs['MCSMaxChannels']     = PV(prefix + 'MaxChannels')
            self.control_pvs['MCSNuseAll']         = PV(prefix + 'NuseAll')

        if 'PvaPlugin' in self.pv_prefixes:
            prefix = self.pv_prefixes['PvaPlugin']
            self.control_pvs['PVANDArrayPort']     = PV(prefix + 'NDArrayPort')                
            self.control_pvs['PVAEnableCallbacks'] = PV(prefix + 'EnableCallbacks')        

        if 'RoiPlugin' in self.pv_prefixes:
            prefix = self.pv_prefixes['RoiPlugin']
            self.control_pvs['ROINDArrayPort']     = PV(prefix + 'NDArrayPort')        
            self.control_pvs['ROIScale']           = PV(prefix + 'Scale')        
            self.control_pvs['ROIBinX']            = PV(prefix + 'BinX')        
            self.control_pvs['ROIBinY']            = PV(prefix + 'BinY')
            self.control_pvs['ROIEnableCallbacks'] = PV(prefix + 'EnableCallbacks')

        if 'CbPlugin' in self.pv_prefixes:
            prefix = self.pv_prefixes['CbPlugin']
            self.control_pvs['CBPortNameRBV']      = PV(prefix + 'PortName_RBV')                    
            self.control_pvs['CBNDArrayPort']      = PV(prefix + 'NDArrayPort')        
            self.control_pvs['CBPreCount']         = PV(prefix + 'PreCount')
            self.control_pvs['CBPostCount']        = PV(prefix + 'PostCount')
            self.control_pvs['CBCapture']          = PV(prefix + 'Capture')            
            self.control_pvs['CBCaptureRBV']       = PV(prefix + 'Capture_RBV')
            self.control_pvs['CBTrigger']          = PV(prefix + 'Trigger')
            self.control_pvs['CBTriggerRBV']       = PV(prefix + 'Trigger_RBV')
            self.control_pvs['CBCurrentQtyRBV']    = PV(prefix + 'CurrentQty_RBV')            
            self.control_pvs['CBEnableCallbacks']  = PV(prefix + 'EnableCallbacks')
            self.control_pvs['CBStatusMessage']    = PV(prefix + 'StatusMessage')

        self.epics_pvs = {**self.config_pvs, **self.control_pvs}
        # Wait 1 second for all PVs to connect
        time.sleep(1)
        self.check_pvs_connected()

        # Configure callbacks on a few PVs
        for epics_pv in ('MoveSampleIn', 'MoveSampleOut', 'StartScan', 'AbortScan', 'ExposureTime',
                         'FilePath', 'FPFilePathExists'):
            self.epics_pvs[epics_pv].add_callback(self.pv_callback)
        for epics_pv in ('MoveSampleIn', 'MoveSampleOut', 'StartScan', 'AbortScan'):
            self.epics_pvs[epics_pv].put(0)
            
        # Synchronize the FilePathExists PV
        self.copy_file_path_exists()

         # Set ^C interrupt to abort the scan
        signal.signal(signal.SIGINT, self.signal_handler)

        # Start the watchdog timer thread
        thread = threading.Thread(target=self.reset_watchdog, args=(), daemon=True)
        thread.start()

    def signal_handler(self, sig, frame):
        """Calls abort_scan when ^C is typed"""
        if sig == signal.SIGINT:
            self.abort_scan()

    def reset_watchdog(self):
        """Sets the watchdog timer to 5 every 3 seconds"""
        while True:
            self.epics_pvs['Watchdog'].put(5)
            time.sleep(3)

    def copy_file_path(self):
        """Copies the FilePath PV to file plugin FilePath"""

        value = self.epics_pvs['FilePath'].get(as_string=True)
        self.epics_pvs['FPFilePath'].put(value, wait=True)

    def copy_file_path_exists(self):
        """Copies the file plugin FilePathExists_RBV PV to FilePathExists"""

        value = self.epics_pvs['FPFilePathExists'].value
        self.epics_pvs['FilePathExists'].put(value)

    def pv_callback(self, pvname=None, value=None, char_value=None, **kw):
        """Callback function that is called by pyEpics when certain EPICS PVs are changed

        The PVs that are handled are:

        - ``StartScan`` : Calls ``run_fly_scan()``

        - ``AbortScan`` : Calls ``abort_scan()``

        - ``MoveSampleIn`` : Runs ``MoveSampleIn()`` in a new thread.

        - ``MoveSampleOut`` : Runs ``MoveSampleOut()`` in a new thread.

        - ``ExposureTime`` : Runs ``set_exposure_time()`` in a new thread.

        - ``FilePath`` : Runs ``copy_file_path`` in a new thread.

        - ``FPFilePathExists`` : Runs ``copy_file_path_exists`` in a new thread.
        """

        log.debug('pv_callback pvName=%s, value=%s, char_value=%s', pvname, value, char_value)
        if (pvname.find('MoveSampleIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_sample_in, args=())
            thread.start()
        elif (pvname.find('MoveSampleOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_sample_out, args=())
            thread.start()
        elif pvname.find('ExposureTime') != -1:
            thread = threading.Thread(target=self.set_exposure_time, args=(value,))
            thread.start()
        elif pvname.find('FilePathExists') != -1:
            thread = threading.Thread(target=self.copy_file_path_exists, args=())
            thread.start()
        elif pvname.find('FilePath') != -1:
            thread = threading.Thread(target=self.copy_file_path, args=())
            thread.start()
        elif (pvname.find('StartScan') != -1) and (value == 1):
            self.run_fly_scan()
        elif (pvname.find('AbortScan') != -1) and (value == 1):
            self.abort_scan()

    def show_pvs(self):
        """Prints the current values of all EPICS PVs in use.

        The values are printed in three sections:

        - config_pvs : The PVs that are part of the scan configuration and
          are saved by save_configuration()

        - control_pvs : The PVs that are used for EPICS control and status,
          but are not saved by save_configuration()

        - pv_prefixes : The prefixes for PVs that are used for the areaDetector camera,
          file plugin, etc.
        """

        print('configPVS:')
        for config_pv in self.config_pvs:
            print(config_pv, ':', self.config_pvs[config_pv].get(as_string=True))

        print('')
        print('controlPVS:')
        for control_pv in self.control_pvs:
            print(control_pv, ':', self.control_pvs[control_pv].get(as_string=True))

        print('')
        print('pv_prefixes:')
        for pv_prefix in self.pv_prefixes:
            print(pv_prefix, ':', self.pv_prefixes[pv_prefix])

    def check_pvs_connected(self):
        """Checks whether all EPICS PVs are connected.

        Returns
        -------
        bool
            True if all PVs are connected, otherwise False.
        """

        all_connected = True
        for key in self.epics_pvs:
            if not self.epics_pvs[key].connected:
                log.error('PV %s is not connected', self.epics_pvs[key].pvname)
                all_connected = False
        return all_connected

    def read_pv_file(self, pv_file_name, macros):
        """Reads a file containing a list of EPICS PVs to be used by TomoScan.


        Parameters
        ----------
        pv_file_name : str
          Name of the file to read
        macros: dict
          Dictionary of macro substitution to perform when reading the file
        """

        pv_file = open(pv_file_name)
        lines = pv_file.read()
        pv_file.close()
        lines = lines.splitlines()
        for line in lines:
            is_config_pv = True
            if line.find('#controlPV') != -1:
                line = line.replace('#controlPV', '')
                is_config_pv = False
            line = line.lstrip()
            # Skip lines starting with #
            if line.startswith('#'):
                continue
            # Skip blank lines
            if line == '':
                continue
            pvname = line
            # Do macro substitution on the pvName
            for key in macros:
                pvname = pvname.replace(key, macros[key])
            # Replace macros in dictionary key with nothing
            dictentry = line
            for key in macros:
                dictentry = dictentry.replace(key, '')
            epics_pv = PV(pvname)
            if is_config_pv:
                self.config_pvs[dictentry] = epics_pv
            else:
                self.control_pvs[dictentry] = epics_pv
            if dictentry.find('PVName') != -1:
                pvname = epics_pv.value
                key = dictentry.replace('PVName', '')
                self.control_pvs[key] = PV(pvname)
            if dictentry.find('PVPrefix') != -1:
                pvprefix = epics_pv.value
                key = dictentry.replace('PVPrefix', '')
                self.pv_prefixes[key] = pvprefix

    def move_sample_in(self):
        """Moves the sample to the in beam position for collecting projections.

        The in-beam position is defined by the ``SampleInX`` and ``SampleInY`` PVs.

        Which axis to move is defined by the ``FlatFieldAxis`` PV,
        which can be ``X``, ``Y``, or ``Both``.
        """

        axis = self.epics_pvs['FlatFieldAxis'].get(as_string=True)
        log.info('move_sample_in axis: %s', axis)
        if axis in ('X', 'Both'):
            position = self.epics_pvs['SampleInX'].value
            self.epics_pvs['SampleX'].put(position, wait=True, timeout=600)

        if axis in ('Y', 'Both'):
            position = self.epics_pvs['SampleInY'].value
            self.epics_pvs['SampleY'].put(position, wait=True, timeout=600)

        if self.epics_pvs['SampleOutAngleEnable'].get() and self.rotation_save != None:
            if self.max_rotation_speed != None:# max_rotation_speed is not initialized when the scan has not been started            
                cur_speed = self.epics_pvs['RotationSpeed'].get()
                self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)                                                    
            self.epics_pvs['Rotation'].put(self.rotation_save, wait=True)          
            if self.max_rotation_speed != None:
                self.epics_pvs['RotationSpeed'].put(cur_speed)
                                
        self.epics_pvs['MoveSampleIn'].put('Done')

    def move_sample_out(self):
        """Moves the sample to the out of beam position for collecting flat fields.

        The out of beam position is defined by the ``SampleOutX`` and ``SampleOutY`` PVs.

        Which axis to move is defined by the ``FlatFieldAxis`` PV,
        which can be ``X``, ``Y``, or ``Both``.
        """

        if self.epics_pvs['SampleOutAngleEnable'].get():
            if self.max_rotation_speed != None:# max_rotation_speed is not initialized when the scan has not been started
                cur_speed = self.epics_pvs['RotationSpeed'].get()
                self.epics_pvs['RotationSpeed'].put(self.max_rotation_speed)
            angle = self.epics_pvs['SampleOutAngle'].get()
            log.info('move_sample_out angle: %s', angle)
            self.rotation_save = self.epics_pvs['Rotation'].get()
            self.epics_pvs['Rotation'].put(angle, wait=True)  
            if self.max_rotation_speed != None:
                self.epics_pvs['RotationSpeed'].put(cur_speed)                        

        axis = self.epics_pvs['FlatFieldAxis'].get(as_string=True)        
        log.info('move_sample_out axis: %s', axis)
        if axis in ('X', 'Both'):
            position = self.epics_pvs['SampleOutX'].value
            self.epics_pvs['SampleX'].put(position, wait=True, timeout=600)

        if axis in ('Y', 'Both'):
            position = self.epics_pvs['SampleOutY'].value
            self.epics_pvs['SampleY'].put(position, wait=True, timeout=600)

        self.epics_pvs['MoveSampleOut'].put('Done')

    def save_configuration(self, file_name):
        """Saves the current configuration PVs to a file.

        A new dictionary is created, containing the key for each PV in the ``config_pvs`` dictionary
        and the current value of that PV.  This dictionary is written to the file in JSON format.

        Parameters
        ----------
        file_name : str
            The name of the file to save to.
        """

        config = {}
        for key in self.config_pvs:
            config[key] = self.config_pvs[key].get(as_string=True)
        out_file = open(file_name, 'w')
        json.dump(config, out_file, indent=2)
        out_file.close()

    def load_configuration(self, file_name):
        """Loads a configuration from a file into the EPICS PVs.

        Parameters
        ----------
        file_name : str
            The name of the file to save to.
        """

        in_file = open(file_name, 'r')
        config = json.load(in_file)
        in_file.close()
        for key in config:
            self.config_pvs[key].put(config[key])

    def open_shutter(self):
        """Opens the shutter to collect flat fields or projections.

        The value in the ``OpenShutterValue`` PV is written to the ``OpenShutter`` PV.
        """

        if not self.epics_pvs['OpenShutter'] is None:
            pv = self.epics_pvs['OpenShutter']
            value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
            log.info('open shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenShutter'].put(value, wait=True)

    def close_shutter(self):
        """Closes the shutter to collect dark fields.

        The value in the ``CloseShutterValue`` PV is written to the ``CloseShutter`` PV.
        """
        if not self.epics_pvs['CloseShutter'] is None:
            pv = self.epics_pvs['CloseShutter']
            value = self.epics_pvs['CloseShutterValue'].get(as_string=True)
            log.info('close shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseShutter'].put(value, wait=True)

    def set_exposure_time(self, exposure_time=None):
        """Sets the camera exposure time.

        The exposure_time is written to the camera's ``AcquireTime`` PV.

        Parameters
        ----------
        exposure_time : float, optional
            The exposure time to use. If None then the value of the ``ExposureTime`` PV is used.
        """
        if not self.scan_is_running:
            if exposure_time is None:
                exposure_time = self.epics_pvs['ExposureTime'].value
            self.epics_pvs['CamAcquireTime'].put(exposure_time, wait=True, timeout = 10.0)

    def set_flat_exposure_time(self, exposure_time=None):
        """Sets the camera exposure time for flat fields.

        The exposure_time is written to the camera's ``AcquireTime`` PV.

        Parameters
        ----------
        exposure_time : float, optional
            The exposure time to use. If None then the value of the ``FlatExposureTime`` PV is used.
        """

        if self.epics_pvs['DifferentFlatExposure'].get(as_string=True) == 'Same':
            self.set_exposure_time(exposure_time)
            return
        if exposure_time is None:
            exposure_time = self.epics_pvs['FlatExposureTime'].value
            log.warning('Setting flat field exposure time: %f s', exposure_time)
        self.epics_pvs['CamAcquireTime'].put(exposure_time, wait=True, timeout = 10.)

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This base class method does the following:

        - Sets the status string in the ``ScanStatus`` PV.

        - Stops the camera acquisition.

        - Calls ``set_exposure_time()``

        - Copies the ``FilePath`` and ``FileName`` PVs to the areaDetector file plugin.

        - Sets class variables with the important scan parameters

        - Checks whether the file that will be saved by the file plugin already exists.
          If it does, and if the OverwriteWarning PV is 'Yes' then it opens a dialog
          box asking the user if they want to overwrite the file.  If they answer 'No'
          then a FileOverwriteError exception is raised.

        It is expected that most derived classes will override this method.  In most cases they
        should first call this base class method, and then perform any beamline-specific operations.
        """

        self.scan_is_running = True
        self.epics_pvs['ScanStatus'].put('Beginning scan')
        # Stop the camera since it could be in free-run mode
        self.epics_pvs['CamAcquire'].put(0, wait=True)
        # Set the exposure time
        self.set_exposure_time()
        # Set the file path, file name and file number
        self.epics_pvs['FPFilePath'].put(self.epics_pvs['FilePath'].value, wait=True)
        self.epics_pvs['FPFileName'].put(self.epics_pvs['FileName'].value, wait=True) 

        # Copy the current values of scan parameters into class variables
        self.exposure_time        = self.epics_pvs['ExposureTime'].value
        self.rotation_start       = self.epics_pvs['RotationStart'].value
        self.rotation_step        = self.epics_pvs['RotationStep'].value
        self.num_angles           = self.epics_pvs['NumAngles'].value
        self.rotation_stop        = self.rotation_start + (self.num_angles * self.rotation_step)
        self.rotation_resolution  = self.epics_pvs['RotationResolution'].value
        self.max_rotation_speed   = self.epics_pvs['RotationMaxSpeed'].value
        self.return_rotation      = self.epics_pvs['ReturnRotation'].get(as_string=True)
        self.num_dark_fields      = self.epics_pvs['NumDarkFields'].value
        self.dark_field_mode      = self.epics_pvs['DarkFieldMode'].get(as_string=True)
        self.num_flat_fields      = self.epics_pvs['NumFlatFields'].value
        self.flat_field_mode      = self.epics_pvs['FlatFieldMode'].get(as_string=True)
        self.file_path_rbv        = self.epics_pvs['FPFilePathRBV'].get(as_string=True)
        self.file_name_rbv        = self.epics_pvs['FPFileNameRBV'].get(as_string=True)
        self.file_number          = self.epics_pvs['FPFileNumber'].value
        self.file_template        = self.epics_pvs['FPFileTemplate'].get(as_string=True)
        self.total_images = self.num_angles
        if self.dark_field_mode != 'None':
            self.total_images += self.num_dark_fields
        if self.dark_field_mode == 'Both':
            self.total_images += self.num_dark_fields
        if self.flat_field_mode != 'None':
            self.total_images += self.num_flat_fields
        if self.flat_field_mode == 'Both':
            self.total_images += self.num_flat_fields

        if self.epics_pvs['OverwriteWarning'].get(as_string=True) == 'Yes':
            # Make sure there is not already a file by this name
            try:
                file_name = self.file_template % (self.file_path_rbv, self.file_name_rbv, self.file_number)
            except:
                try:
                    file_name = self.file_template % (self.file_path_rbv, self.file_name_rbv)
                except:
                    try:
                        file_name = self.file_template % (self.file_path_rbv)
                    except:
                        log.error("File name template: %s not supported", self.file_template)
                        raise TypeError
            if os.path.exists(file_name):
                self.epics_pvs['ScanStatus'].put('Waiting for overwrite confirmation')
                reply = pymsgbox.confirm('File ' + file_name + ' exists.  Overwrite?',
                                         'Overwrite file', ['Yes', 'No'])
                if reply == 'No':
                    raise FileOverwriteError



    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This base class method does the following:

        - Sets the status string in the ``ScanStatus`` PV.

        - If the ``ReturnRotation`` PV is Yes then it moves the rotation motor back to the
          position defined by the ``RotationStart`` PV.  It does not wait for the move to complete.

        - Sets the ``StartScan`` PV to 0.  This PV is an EPICS ``busy`` record.
          Normally EPICS clients that start a scan with the ``StartScan`` PV will wait for
          ``StartScan`` to return to 0, often using the ``ca_put_callback()`` mechanism.

        It is expected that most derived classes will override this method.  In most cases they
        should first perform any beamline-specific operations and then call this base class method.
        This ensures that the scan is really complete before ``StartScan`` is set to 0.
        """

        if self.return_rotation == 'Yes':
            self.epics_pvs['Rotation'].put(self.rotation_start)
        log.info('Scan complete')
        self.epics_pvs['ScanStatus'].put('Scan complete')
        self.epics_pvs['StartScan'].put(0)
        self.scan_is_running = False

    def fly_scan(self):
        """Performs the operations for a tomography fly scan, i.e. with continuous rotation.

        This base class method does the following:

        - Moves the rotation motor to position defined by the ``RotationStart`` PV.

        - Calls ``begin_scan()``

        - If the ``DarkFieldMode`` PV is 'Start' or 'Both' calls ``collect_dark_fields()``

        - If the ``FlatFieldMode`` PV is 'Start' or 'Both' calls ``collect_flat_fields()``

        - Calls ``collect_projections()``

        - If the ``FlatFieldMode`` PV is 'End' or 'Both' calls ``collect_flat_fields()``

        - If the ``DarkFieldMode`` PV is 'End' or 'Both' calls ``collect_dark_fields()``

        - Calls ``end_scan``

        If there is either CameraTimeoutError exception or ScanAbortError exception during the scan,
        it jumps immediate to calling ``end_scan()`` and returns.

        It is not expected that most derived classes will need to override this method, but they are
        free to do so if required.
        """

        try:
            # Prepare for scan
            self.begin_scan()
            # Move the rotation to the start
            self.epics_pvs['Rotation'].put(self.rotation_start, wait=True)
            # Collect the pre-scan dark fields if required
            if (self.num_dark_fields > 0) and (self.dark_field_mode in ('Start', 'Both')):
                self.collect_dark_fields()
            # Collect the pre-scan flat fields if required
            if (self.num_flat_fields > 0) and (self.flat_field_mode in ('Start', 'Both')):
                self.collect_flat_fields()
            # Collect the projections
            self.collect_projections()
            # Collect the post-scan flat fields if required
            if (self.num_flat_fields > 0) and (self.flat_field_mode in ('End', 'Both')):
                self.collect_flat_fields()
            # Collect the post-scan dark fields if required
            if (self.num_dark_fields > 0) and (self.dark_field_mode in ('End', 'Both')):
                self.collect_dark_fields()
 
        except ScanAbortError:
            log.error('Scan aborted')
        except CameraTimeoutError:
            log.error('Camera timeout')
        except FileOverwriteError:
            log.error('File overwrite aborted')
        #Make sure we do cleanup tasks from the end of the scan
        finally:
            self.end_scan()

    def run_fly_scan(self):
        """Runs ``fly_scan()`` in a new thread."""

        thread = threading.Thread(target=self.fly_scan, args=())
        thread.start()

    def collect_dark_fields(self):
        """Collects dark field data

        This base class method does the following:

          - Sets the scan status message

          - Calls close_shutter()

          - Sets the HDF5 data location for dark fields

          - Sets the FrameType to "DarkField"

        Derived classes must override this method to actually collect the dark fields.
        In most cases they should call this base class method first and then perform
        the beamline-specific operations.
        """
        self.epics_pvs['ScanStatus'].put('Collecting dark fields')
        self.set_exposure_time()
        self.close_shutter()
        self.epics_pvs['HDF5Location'].put(self.epics_pvs['HDF5DarkLocation'].value)
        self.epics_pvs['FrameType'].put('DarkField')

    def collect_flat_fields(self):
        """Collects flat field data

        This base class method does the following:

          - Sets the scan status message

          - Calls open_shutter()

          - Calls move_sample_out()

          - Sets the HDF5 data location for flat fields

          - Sets the FrameType to "FlatField"

        Derived classes must override this method to actually collect the flat fields.
        In most cases they should call this base class method first and then perform
        the beamline-specific operations.
        """
        self.epics_pvs['ScanStatus'].put('Collecting flat fields')
        self.set_flat_exposure_time()
        self.open_shutter()
        self.move_sample_out()
        self.epics_pvs['HDF5Location'].put(self.epics_pvs['HDF5FlatLocation'].value)
        self.epics_pvs['FrameType'].put('FlatField')

    def collect_projections(self):
        """Collects projection data

        This base class method does the following:

          - Sets the scan status message

          - Calls open_shutter()

          - Calls move_sample_in()

          - Sets the HDF5 data location for projection data

          - Sets the FrameType to "Projection"

        Derived classes must override this method to actually collect the projections.
        In most cases they should call this base class method first and then perform
        the beamline-specific operations.
        """
        self.epics_pvs['ScanStatus'].put('Collecting projections')
        self.set_exposure_time()
        self.open_shutter()
        self.move_sample_in()
        self.epics_pvs['HDF5Location'].put(self.epics_pvs['HDF5ProjectionLocation'].value)
        self.epics_pvs['FrameType'].put('Projection')

    def abort_scan(self):
        """Aborts a scan that is running and performs the operations 
        needed when a scan is aborted.

        This does the following:

        - Sets scan_is_running, a flag that is checked in ``wait_camera_done()``.
          If ``wait_camera_done()`` finds the flag set then it raises a 
          ScanAbortError exception.

        - Stops the rotation motor.

        - Stops the file saving plugin.
        """

        self.scan_is_running = False

        # Stop the rotation motor
        self.epics_pvs['RotationStop'].put(1)
        # Stop the file plugin
        self.epics_pvs['FPCapture'].put(0) # see https://github.com/tomography/tomoscan/issues/127

    def compute_frame_time(self):
        """Computes the time to collect and readout an image from the camera.

        This method is used to compute the time between triggers to the camera.
        This can be used, for example, to configure a trigger generator or to compute
        the speed of the rotation stage.

        The calculation is camera specific.  The result can depend on the actual exposure time
        of the camera, and on a variety of camera configuration settings (pixel binning,
        pixel bit depth, video mode, etc.)

        The current version only supports the Point Grey Grasshopper3 GS3-U3-23S6M.
        The logic for additional cameras should be added to this function in the future
        if the camera is expected to be used at more than one beamline.
        If the camera is only to be used at a single beamline then the code should be added
        to this method in the derived class

        Returns
        -------
        float
            The frame time, which is the minimum time allowed between triggers for the value of the
            ``ExposureTime`` PV.
        """
        # The readout time of the camera depends on the model, and things like the
        # PixelFormat, VideoMode, etc.
        # The measured times in ms with 100 microsecond exposure time and 1000 frames
        # without dropping
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        readout = None
        video_mode = None
        # Adding 1% read out margin to the exposure time, and at least 1 ms seems to work for FLIR cameras
        # This is empirical and if needed should adjusted for each camera
        readout_margin = 1.01
        if camera_model == 'Grasshopper3 GS3-U3-23S6M':
            pixel_format = self.epics_pvs['CamPixelFormat'].get(as_string=True) 
            video_mode   = self.epics_pvs['CamVideoMode'].get(as_string=True)
            readout_times = {
                'Mono8':        {'Mode0': 6.2,  'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 7.9},
                'Mono12Packed': {'Mode0': 9.2,  'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 11.5},
                'Mono16':       {'Mode0': 12.2, 'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 12.2}
            }
            readout = readout_times[pixel_format][video_mode]/1000.
        if camera_model == 'Grasshopper3 GS3-U3-51S5M':
            pixel_format = self.epics_pvs['CamPixelFormat'].get(as_string=True) 
            readout_times = {
                'Mono8': 6.18,
                'Mono12Packed': 8.20,
                'Mono12p': 8.20,
                'Mono16': 12.34
            }
            readout = readout_times[pixel_format]/1000.            
        if camera_model == 'Oryx ORX-10G-51S5M':
            pixel_format = self.epics_pvs['CamPixelFormat'].get(as_string=True) 
            readout_margin = 1.02
            readout_times = {
                'Mono8': 6.18,
                'Mono12Packed': 8.20,
                'Mono16': 12.34
            }
            readout = readout_times[pixel_format]/1000.
        if camera_model == 'Oryx ORX-10G-310S9M':
            pixel_format = self.epics_pvs['CamPixelFormat'].get(as_string=True) 
            readout_times = {
                'Mono8': 30.0,
                'Mono12Packed': 30.0,
                'Mono16': 30.0
            }
            readout = readout_times[pixel_format]/1000.
        if camera_model == 'Q-12A180-Fm/CXP-6':
            pixel_format = self.epics_pvs['CamPixelFormat'].get(as_string=True) 
            readout_times = {
                'Mono8': 5.35
            }        
            readout = readout_times[pixel_format]/1000.
        if camera_model == 'Blackfly S BFS-PGE-161S7M':
            pixel_format = self.epics_pvs['CamPixelFormat'].get(as_string=True) 
            readout_times = {
                'Mono8': 83.4,
                'Mono12Packed': 100.0,
                'Mono16': 142.86
            }
            readout_margin = 1.035
            readout = readout_times[pixel_format]/1000.

        if readout is None:
            log.error('Unsupported combination of camera model, pixel format and video mode: %s %s %s',
                          camera_model, pixel_format, video_mode)            
            return 0

        # We need to use the actual exposure time that the camera is using, not the requested time
        exposure = self.epics_pvs['CamAcquireTimeRBV'].value
        # Add some extra time to exposure time for margin.
        frame_time = exposure * readout_margin        
        # If the time is less than the readout time then use the readout time plus 1 ms.
        if frame_time < readout:
            frame_time = readout + .001
        return frame_time

    def update_status(self, start_time):
        """
        When called updates ``ImagesCollected``, ``ImagesSaved``, ``ElapsedTime``, and ``RemainingTime``. 

        Parameters
        ----------
        start_time : time

            Start time to calculate elapsed time.

        Returns
        -------
        elapsed_time : float

            Elapsed time to be used for time out.
        """
        num_collected  = self.epics_pvs['CamNumImagesCounter'].value
        num_images     = self.epics_pvs['CamNumImages'].value
        num_saved      = self.epics_pvs['FPNumCaptured'].value
        num_to_save     = self.epics_pvs['FPNumCapture'].value
        current_time = time.time()
        elapsed_time = current_time - start_time
        remaining_time = (elapsed_time * (num_images - num_collected) /
                          max(float(num_collected), 1))
        collect_progress = str(num_collected) + '/' + str(num_images)
        log.info('Collected %s', collect_progress)
        self.epics_pvs['ImagesCollected'].put(collect_progress)
        save_progress = str(num_saved) + '/' + str(num_to_save)
        log.info('Saved %s', save_progress)
        self.epics_pvs['ImagesSaved'].put(save_progress)
        self.epics_pvs['ElapsedTime'].put(str(timedelta(seconds=int(elapsed_time))))
        self.epics_pvs['RemainingTime'].put(str(timedelta(seconds=int(remaining_time))))

        return elapsed_time

    def wait_camera_done(self, timeout):
        """Waits for the camera acquisition to complete, or for ``abort_scan()`` to be called.

        While waiting this method periodically updates the status PVs ``ImagesCollected``,
        ``ImagesSaved``, ``ElapsedTime``, and ``RemainingTime``.

        Parameters
        ----------
        timeout : float
            The maximum number of seconds to wait before raising a CameraTimeoutError exception.

        Raises
        ------
        ScanAbortError
            If ``abort_scan()`` is called
        CameraTimeoutError
            If acquisition has not completed within timeout value.
        """

        start_time = time.time()
        while True:
            if self.epics_pvs['CamAcquireBusy'].value == 0:
                return
            if not self.scan_is_running:
                raise ScanAbortError
            time.sleep(0.2)
            elapsed_time = self.update_status(start_time)
            if timeout > 0:
                if elapsed_time >= timeout:
                    raise CameraTimeoutError()
