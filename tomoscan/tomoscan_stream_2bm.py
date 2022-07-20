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
    TomoScanStream2BM
        Derived class for tomography scanning in streaming mode with EPICS at APS beamline 2-BM
"""
import os
import time
import h5py 
import numpy as np

from tomoscan import TomoScanStreamPSO
from tomoscan import log
from tomoscan import util
import threading
import pvaccess
from epics import PV


EPSILON = .001

class TomoScanStream2BM(TomoScanStreamPSO):
    """Derived class used for tomography scanning in streamaing mode with EPICS at APS beamline 2-BM

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
        #self.set_trigger_mode('Internal', 1)
        
        # set TomoScan xml files
        self.epics_pvs['CamNDAttributesFile'].put('TomoScanDetectorAttributes.xml')
        self.epics_pvs['FPXMLFileName'].put('TomoScanLayout.xml')
        macro = 'DET=' + self.pv_prefixes['Camera'] + ',' + 'TS=' + self.epics_pvs['Testing'].__dict__['pvname'].replace('Testing', '', 1)
        self.control_pvs['CamNDAttributesMacros'].put(macro)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Set standard file template on file writer
        self.epics_pvs['FPFileTemplate'].put("%s%s_%3.3d.h5", wait=True)

        # Disable overw writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')
        
        # Lens change functionality
        prefix = self.pv_prefixes['MctOptics']
        self.epics_pvs['LensSelect'] = PV(prefix+'LensSelect')            
        # # ref to pixel size
        # self.epics_pvs['MCTPixelSize'] = PV(prefix+'PixelSize')            
        # # 
        # self.epics_pvs['PixelSize'].put(self.epics_pvs['MCTPixelSize'])

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
            log.warning("Wait 2s  - Temporarily while there is no fast shutter at 2bmb ")
            time.sleep(2)

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
            log.warning('close fast shutter sleep 2 sec')
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
        if(camera_model=='Oryx ORX-10G-51S5M'):            
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
            self.epics_pvs['CamImageMode'].put('Continuous')     # switched to Continuous for tomostream       
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateEnable'].put(0)

            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
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
            #self.epics_pvs['CamAcquire'].put('Acquire')
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

        """
        log.info('begin scan')

        # Set data directory
        file_path = self.epics_pvs['DetectorTopDir'].get(as_string=True) + self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + os.path.sep + self.epics_pvs['UserLastName'].get(as_string=True) + os.path.sep
        self.epics_pvs['FilePath'].put(file_path, wait=True)

        
        if self.epics_pvs['ReturnRotation'].get(as_string=True) == 'Yes':
            if np.abs(self.epics_pvs['RotationRBV'].get())>720:
                log.warning('home stage')
                self.epics_pvs['RotationHomF'].put(1, wait=True)                  
        
        self.lens_cur = self.epics_pvs['LensSelect'].get()
        # Call the base class method
        super().begin_scan()
        # Opens the front-end shutter
        self.open_frontend_shutter()
        self.epics_pvs['LensSelect'].add_callback(self.pv_callback_stream_2bm)
        
    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:
        - Calls ``save_configuration()``.
        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.

        - Closes shutter.
        """
        
        if self.epics_pvs['ReturnRotation'].get(as_string=True) == 'Yes':        
            while True:
                ang1 = self.epics_pvs['RotationRBV'].value
                time.sleep(1)
                ang2 = self.epics_pvs['RotationRBV'].value
                print(ang1,ang2)
                if np.abs(ang1-ang2)<1e-4:
                    break
            if np.abs(self.epics_pvs['RotationRBV'].value)>720:
                log.warning('home stage')
                self.epics_pvs['RotationHomF'].put(1, wait=True)                        
        self.epics_pvs['LensSelect'].clear_callbacks()
        # Call the base class method
        super().end_scan()
        # Close shutter
        self.close_shutter()
    
    def pv_callback_stream_2bm(self, pvname=None, value=None, char_value=None, **kw):
        """Callback functions for capturing in the streaming mode"""
        if (pvname.find('LensSelect') != -1 and (value==0 or value==1 or value==2)):
            thread = threading.Thread(target=self.lens_change_sync, args=())
            thread.start() 
    
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

    def lens_change_sync(self):
        """Save/Update dark and flat fields for lenses"""
        
        # ref to pixel size
        # self.epics_pvs['MCTPixelSize'] = PV(prefix+'PixelSize')            
        # 
        # self.epics_pvs['PixelSize'].put(self.epics_pvs['MCTPixelSize'])

        log.info(f'switch lens from {self.lens_cur}')
        dirname = os.path.dirname(self.epics_pvs['FPFullFileName'].get(as_string=True))            
        cmd = 'cp '+ dirname+'/dark_fields.h5 '+ dirname+'/dark_fields_'+str(self.lens_cur)+'.h5 2> /dev/null '
        os.system(cmd)                
        cmd = 'cp '+ dirname+'/flat_fields.h5 '+ dirname+'/flat_fields_'+str(self.lens_cur)+'.h5 2> /dev/null '
        os.system(cmd)                
        self.lens_cur = self.epics_pvs['LensSelect'].get()
        log.info(f'to {self.lens_cur}')
        cmd = 'cp '+ dirname+'/dark_fields_'+str(self.lens_cur)+'.h5 '+ dirname+'/dark_fields.h5 2> /dev/null '
        os.system(cmd)                
        cmd = 'cp '+ dirname+'/flat_fields_'+str(self.lens_cur)+'.h5 '+ dirname+'/flat_fields.h5 2> /dev/null '
        os.system(cmd)   
        self.broadcast_dark()             
        self.broadcast_flat()             
                
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
