"""Software for tomography scanning with EPICS at APS beamline 32-ID

   Classes
   -------
   TomoScan32ID
     Derived class for tomography scanning with EPICS at APS beamline 32-ID
"""
import time
import os
import h5py 
import sys
import traceback
import numpy as np
from epics import PV
import threading

from tomoscan import data_management as dm
from tomoscan import TomoScanPSO
from tomoscan import log

EPSILON = .001

class TomoScan32ID(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 32-ID

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

        # TXM Optics IOCs
        if 'CRLRelays' in self.pv_prefixes:
            prefix = self.pv_prefixes['CRLRelays']
            self.control_pvs['CRLRelaysY0']       = PV(prefix + 'oY0')
            self.control_pvs['CRLRelaysY1']       = PV(prefix + 'oY1')
            self.control_pvs['CRLRelaysY2']       = PV(prefix + 'oY2')
            self.control_pvs['CRLRelaysY3']       = PV(prefix + 'oY3')
            self.control_pvs['CRLRelaysY4']       = PV(prefix + 'oY4')
            self.control_pvs['CRLRelaysY5']       = PV(prefix + 'oY5')
            self.control_pvs['CRLRelaysY6']       = PV(prefix + 'oY6')
            self.control_pvs['CRLRelaysY7']       = PV(prefix + 'oY7')

        if 'ValvesPLC' in self.pv_prefixes:
            prefix = self.pv_prefixes['ValvesPLC']
            # Sample stack
            self.control_pvs['VPLCHighPressureOn']     = PV(prefix + 'oC23')
            self.control_pvs['VPLCHighPressureOff']    = PV(prefix + 'oC33')
            self.control_pvs['VPLCHighPressureStatus'] = PV(prefix + 'C3')
            self.control_pvs['VPLCLowPressureXOn']     = PV(prefix + 'oC22')
            self.control_pvs['VPLCLowPressureXOff']    = PV(prefix + 'oC32')
            self.control_pvs['VPLCLowPressureXStatus'] = PV(prefix + 'oC2')
            self.control_pvs['VPLCLowPressureYOn']     = PV(prefix + 'oC21')
            self.control_pvs['VPLCLowPressureYOff']    = PV(prefix + 'oC31')
            self.control_pvs['VPLCLowPressureYStatus'] = PV(prefix + 'oC1')
            self.control_pvs['VPLCHeFlow']             = PV(prefix + 'ao1')

        if 'Shaker' in self.pv_prefixes:
            prefix = self.pv_prefixes['Shaker']
            self.control_pvs['ShakerRun']             = PV(prefix + 'run')
            self.control_pvs['ShakerFrequency']       = PV(prefix + 'frequency')
            self.control_pvs['ShakerTimePerPoint']    = PV(prefix + 'timePerPoint')
            self.control_pvs['ShakerNumPoints']       = PV(prefix + 'numPoints')
            self.control_pvs['ShakerAAmpMuliplyer']   = PV(prefix + 'A:ampMult')
            self.control_pvs['ShakerAAmpOffset']      = PV(prefix + 'A:ampOffset')
            self.control_pvs['ShakerAPhaseShift']     = PV(prefix + 'A:phaseShift')
            self.control_pvs['ShakerBAmpMuliplyer']   = PV(prefix + 'B:ampMult')
            self.control_pvs['ShakerBAmpOffset']      = PV(prefix + 'B:ampOffset')
            self.control_pvs['ShakerBFreqMult']       = PV(prefix + 'B:freqMult')

        if 'BPM' in self.pv_prefixes:
            prefix = self.pv_prefixes['BPM']
            self.control_pvs['BPMHSetPoint']          = PV(prefix + 'fb4.VAL')
            self.control_pvs['BPMHReadBack']          = PV(prefix + 'fb4.CVAL')
            self.control_pvs['BPMHFeedback']          = PV(prefix + 'fb4.FBON')
            self.control_pvs['BPMHUpdateRate']        = PV(prefix + 'fb4.SCAN')
            self.control_pvs['BPMHKP']                = PV(prefix + 'fb4.KP')
            self.control_pvs['BPMHKI']                = PV(prefix + 'fb4.KI')
            self.control_pvs['BPMHKD']                = PV(prefix + 'fb4.KD')
            self.control_pvs['BPMHI']                 = PV(prefix + 'fb4.I')
            self.control_pvs['BPMHLowLimit']          = PV(prefix + 'fb4.DRVL')
            self.control_pvs['BPMHHighLimit']         = PV(prefix + 'fb4.DRVH')
            self.control_pvs['BPMVSetPoint']          = PV(prefix + 'fb3.VAL')
            self.control_pvs['BPMVReadBack']          = PV(prefix + 'fb3.CVAL')
            self.control_pvs['BPMVFeedback']          = PV(prefix + 'fb3.FBON')
            self.control_pvs['BPMVUpdateRate']        = PV(prefix + 'fb3.SCAN')
            self.control_pvs['BPMVKP']                = PV(prefix + 'fb3.KP')
            self.control_pvs['BPMVKI']                = PV(prefix + 'fb3.KI')
            self.control_pvs['BPMVKD']                = PV(prefix + 'fb3.KD')
            self.control_pvs['BPMVI']                 = PV(prefix + 'fb3.I')
            self.control_pvs['BPMVLowLimit']          = PV(prefix + 'fb3.DRVL')
            self.control_pvs['BPMVHighLimit']         = PV(prefix + 'fb3.DRVH')

        self.epics_pvs = {**self.config_pvs, **self.control_pvs}
        
        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Set standard file template on file writer
        self.epics_pvs['FPFileTemplate'].put("%s%s_%3.3d.h5", wait=True)

        # Disable over writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')


        for epics_pv in ('MoveCRLIn', 'MoveCRLOut', 'MovePhaseRingIn', 'MovePhaseRingOut', 'MoveDiffuserIn',
                         'MoveDiffuserOut', 'MoveBeamstopIn', 'MoveBeamstopOut', 'MovePinholeIn', 'MovePinholeOut',
                         'MoveCondenserIn', 'MoveCondenserOut', 'MoveZonePlateIn', 'MoveZonePlateOut',
                         'MoveAllIn', 'MoveAllOut'):
            self.epics_pvs[epics_pv].add_callback(self.pv_callback_32id)

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

        - Closes the 32-ID-C front-end shutter.

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

        - Closes the 32-ID-C fast shutter.
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
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        if(camera_model=='Grasshopper3 GS3-U3-51S5M'):        
            self.set_trigger_mode_grasshopper(trigger_mode, num_images)
        else:
            log.error('Camera is not supported')
            exit(1)

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

        # set TomoScan xml files
        self.epics_pvs['CamNDAttributesFile'].put('TomoScanDetectorAttributes.xml')
        self.epics_pvs['FPXMLFileName'].put('TomoScanLayout.xml')

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
            current_angle = self.epics_pvs['Rotation'].get() %360
            self.epics_pvs['RotationSet'].put('Set', wait=True)
            self.epics_pvs['Rotation'].put(current_angle, wait=True)
            self.epics_pvs['RotationSet'].put('Use', wait=True)
        # Call the base class method
        super().end_scan()
        # Close shutter
        self.close_shutter()

        # Stop the file plugin
        self.epics_pvs['FPCapture'].put('Done')
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)
        # Add theta in the hdf file
        self.add_theta()

        # Copy raw data to data analysis computer    
        if self.epics_pvs['CopyToAnalysisDir'].get():
            log.info('Automatic data trasfer to data analysis computer is enabled.')
            full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
            remote_analysis_dir = self.epics_pvs['RemoteAnalysisDir'].get(as_string=True)
            dm.scp(full_file_name, remote_analysis_dir)
        else:
            log.warning('Automatic data trasfer to data analysis computer is disabled.')
    
    def set_exposure_time(self, exposure_time=None):

        camera_model = self.epics_pvs['CamModel'].get(as_string=True)        
        if(camera_model=='Q-12A180-Fm/CXP-6'):
            if exposure_time is None:
                exposure_time = self.epics_pvs['ExposureTime'].value            
            self.epics_pvs['CamAcquisitionFrameRate'].put(1/exposure_time, wait=True, timeout=10.0) 
            self.epics_pvs['CamAcquireTime'].put(exposure_time, wait=True, timeout = 10.0)
        else:
            super().set_exposure_time(exposure_time)

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

    def move_crl_in(self):
        """Moves the crl in.
        """
        self.control_pvs['CRLRelaysY0'].put(1, wait=True, timeout=1)
        # self.control_pvs['CRLRelaysY1'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY2'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY3'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY4'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY5'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY6'].put(1, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY7'].put(1, wait=True, timeout=1)

        self.epics_pvs['MoveCRLIn'].put('Done')

    def move_crl_out(self):
        """Moves the crl out.
        """
        self.control_pvs['CRLRelaysY0'].put(0, wait=True, timeout=1)
        # self.control_pvs['CRLRelaysY1'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY2'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY3'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY4'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY5'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY6'].put(0, wait=True, timeout=1)
        self.control_pvs['CRLRelaysY7'].put(0, wait=True, timeout=1)

        self.epics_pvs['MoveCRLOut'].put('Done')

    def move_diffuser_in(self):
        """Moves the diffuser in.
        """
        position = self.epics_pvs['DiffuserInX'].value
        self.epics_pvs['DiffuserX'].put(position, wait=True)

        self.epics_pvs['MoveDiffuserIn'].put('Done')

    def move_diffuser_out(self):
        """Moves the diffuser out.
        """
        position = self.epics_pvs['DiffuserOutX'].value
        self.epics_pvs['DiffuserX'].put(position, wait=True)

        self.epics_pvs['MoveDiffuserOut'].put('Done')

    def move_beamstop_in(self):
        """Moves the beamstop in.
        """
        position = self.epics_pvs['BeamstopInY'].value
        self.epics_pvs['BeamstopY'].put(position, wait=True)

        self.epics_pvs['MoveBeamstopIn'].put('Done')

    def move_beamstop_out(self):
        """Moves the beamstop out.
        """
        position = self.epics_pvs['BeamstopOutY'].value
        self.epics_pvs['BeamstopY'].put(position, wait=True)

        self.epics_pvs['MoveBeamstopOut'].put('Done')

    def move_pinhole_in(self):
        """Moves the pinhole in.
        """
        print(f'Move pinhole in')
        position = self.epics_pvs['PinholeInY'].value
        self.epics_pvs['PinholeY'].put(position, wait=True)

        self.epics_pvs['MovePinholeIn'].put('Done')

    def move_pinhole_out(self):
        """Moves the pinhole out.
        """
        position = self.epics_pvs['PinholeOutY'].value
        self.epics_pvs['PinholeY'].put(position, wait=True)

        self.epics_pvs['MovePinholeOut'].put('Done')

    def move_condenser_in(self):
        """Moves the condenser in.
        """
        position = self.epics_pvs['CondenserInY'].value
        self.epics_pvs['CondenserY'].put(position, wait=True)

        self.epics_pvs['MoveCondenserIn'].put('Done')

    def move_condenser_out(self):
        """Moves the condenser out.
        """
        position = self.epics_pvs['CondenserOutY'].value
        self.epics_pvs['CondenserY'].put(position, wait=True)

        self.epics_pvs['MoveCondenserOut'].put('Done')

    def move_zoneplate_in(self):
        """Moves the zone plate in.
        """
        position = self.epics_pvs['ZonePlateInY'].value
        self.epics_pvs['ZonePlateY'].put(position, wait=True)

        self.epics_pvs['MoveZonePlateIn'].put('Done')

    def move_zoneplate_out(self):
        """Moves the zone plate out.
        """
        position = self.epics_pvs['ZonePlateOutY'].value
        self.epics_pvs['ZonePlateY'].put(position, wait=True)

        self.epics_pvs['MoveZonePlateOut'].put('Done')

    def move_PhaseRing_in(self):
        """Moves the phase ring in.
        """
        position = self.epics_pvs['PhaseRingInX'].value
        self.epics_pvs['PhaseRingX'].put(position, wait=True)
        position = self.epics_pvs['PhaseRingInY'].value
        self.epics_pvs['PhaseRingY'].put(position, wait=True)

        self.epics_pvs['MovePhaseRingIn'].put('Done')

    def move_PhaseRing_out(self):
        """Moves the phase ring out.
        """
        position = self.epics_pvs['PhaseRingOutX'].value
        self.epics_pvs['PhaseRingX'].put(position, wait=True)
        position = self.epics_pvs['PhaseRingOutY'].value
        self.epics_pvs['PhaseRingY'].put(position, wait=True)

        self.epics_pvs['MovePhaseRingOut'].put('Done')

    def move_all_in(self):
        """Moves all in
        """        
        self.move_crl_in()
#       self.move_phasering_in() # VN: not needed for absorption contrast
        self.move_diffuser_in()
        self.move_beamstop_in()
        self.move_pinhole_in()
        self.move_condenser_in()
#        self.move_zoneplate_in() # VN: better not to move ZP

    def move_all_out(self):
        """Moves all out
        """        
        self.move_crl_out()
#       self.move_phasering_out() # VN: not needed for absorption contrast
        self.move_diffuser_out()
        self.move_beamstop_out()
        self.move_pinhole_out()
        self.move_condenser_out()
#        self.move_zoneplate_in() # VN: better not to move ZP

    def pv_callback_32id(self, pvname=None, value=None, char_value=None, **kw):
        """Callback function that is called by pyEpics when certain EPICS PVs are changed        
        """

        log.debug('pv_callback pvName=%s, value=%s, char_value=%s', pvname, value, char_value)
        if (pvname.find('MoveCRLIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_crl_in, args=())
            thread.start()
        elif (pvname.find('MoveCRLOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_crl_out, args=())
            thread.start()
        elif (pvname.find('MovePhaseRingIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_phasering_in, args=())
            thread.start()
        elif (pvname.find('MovePhaseRingOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_phasering_out, args=())
            thread.start()            
        elif (pvname.find('MoveDiffuserIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_diffuser_in, args=())
            thread.start()                        
        elif (pvname.find('MoveDiffuserOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_diffuser_out, args=())
            thread.start()                                    
        elif (pvname.find('MoveBeamstopIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_beamstop_in, args=())
            thread.start()                        
        elif (pvname.find('MoveBeamstopOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_beamstop_out, args=())
            thread.start()                                    
        elif (pvname.find('MovePinholeIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_pinhole_in, args=())
            thread.start()                        
        elif (pvname.find('MovePinholeOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_pinhole_out, args=())
            thread.start()                                    
        elif (pvname.find('MoveCondenserIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_condenser_in, args=())
            thread.start()                        
        elif (pvname.find('MoveCondenserOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_condenser_out, args=())
            thread.start()                                    
        elif (pvname.find('MoveZonePlateIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_zoneplate_in, args=())
            thread.start()                        
        elif (pvname.find('MoveZonePlateOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_zoneplate_out, args=())
            thread.start()        
        elif (pvname.find('MoveAllIn') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_all_in, args=())
            thread.start()                        
        elif (pvname.find('MoveAllOut') != -1) and (value == 1):
            thread = threading.Thread(target=self.move_all_out, args=())
            thread.start()       

