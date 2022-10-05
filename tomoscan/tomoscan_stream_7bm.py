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
import traceback
import os
import time
from pathlib import Path
import h5py 
import numpy as np

from tomoscan.tomoscan_stream_pso import TomoScanStreamPSO
from tomoscan import log
from tomoscan import util
import threading
import pvaccess

EPSILON = .001

class TomoScanStream7BM(TomoScanStreamPSO):
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

        # Set the detector running in FreeRun mode
        self.set_trigger_mode('FreeRun', 1)
        
        # Set data directory
        file_path = Path(self.epics_pvs['DetectorTopDir'].get(as_string=True))
        #file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + '-'
                                       + self.epics_pvs['UserLastName'].get(as_string=True) + '-'
                                       + self.epics_pvs['ProposalNumber'].get(as_string=True)) 
        self.epics_pvs['FilePath'].put(str(file_path), wait=True)
        
        macro = 'DET=' + self.pv_prefixes['Camera'] + ',' + 'TC=' + self.epics_pvs['Testing'].__dict__['pvname'].replace('Testing', '', 1)
        self.control_pvs['CamNDAttributesMacros'].put(macro)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Set standard file template on file writer
        self.epics_pvs['FPFileTemplate'].put("%s%s_%3.3d.h5", wait=True)

        # Disable overwriting warning
        self.epics_pvs['OverwriteWarning'].put('Yes')        
        
    
    def open_shutter(self):
        """Opens the shutter to collect flat fields or projections.

        This does the following:

        - Checks if we are in testing mode.  If we are, do nothing.

        - Opens the front end shutter, waiting for it to indicate it is open.
            This is copied from the 2-BM implementation 9/2020

        - Opens the 7-BM-B fast shutter.
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
        """Closes the shutter to collect dark fields and at the end of a scan
        This does the following:

        - Checks if we are in testing mode.  If we are, do nothing

        - Closes the 7-BM-B fast shutter.

        - Closes the beamline shutter.
       """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not closing shutters.')
            return
        # Close 7-BM-B fast shutter; don't wait for it
        if not self.epics_pvs['CloseFastShutter'] is None:
            pv = self.epics_pvs['CloseFastShutter']
            value = self.epics_pvs['CloseFastShutterValue'].get(as_string=True)
            log.info('close fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseFastShutter'].put(value, wait=False)
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

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode for the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
            This is used to set the ``NumImages`` PV of the camera.
        """
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamAcquire'].put('Acquire')
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else: # set camera to external triggering
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            ext_source = str(self.epics_pvs['ExternalTriggerSource'].get())
            self.epics_pvs['CamTriggerSource'].put(ext_source, wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)

            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateEnable'].put(0)

            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)

            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 1)

    
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
        
        
        log.info('end scan')

        # Close the shutter
        self.close_shutter()

        # Stop the file plugin, though it should be done already
        self.epics_pvs['FPCapture'].put('Done')
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)

        # Add theta in the hdf file
        #self.add_theta()

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

    def wait_pv(self, epics_pv, wait_val, timeout=np.inf, delta_t=0.01):
        """Wait on a pv to be a value until max_timeout (default forever)
           delay for pv to change
        """
        time.sleep(delta_t)
        start_time = time.time()
        while time.time() - start_time < timeout:
            pv_val = epics_pv.get()
            if isinstance(pv_val, float):
                if abs(pv_val - wait_val) < EPSILON:
                    return True
            if pv_val == wait_val:
                return True
            time.sleep(delta_t)
        else:
            log.error('  *** ERROR: PV TIMEOUT ***')
            log.error('  *** wait_pv(%s, %d, %5.2f reached max timeout. Return False',
                          epics_pv.pvname, wait_val, timeout)
            return False        
    
    def auto_copy_data(self):
        '''Copies data from detector computer to analysis computer.
        '''
        # Copy raw data to data analysis computer    
        if self.epics_pvs['CopyToAnalysisDir'].get():
            log.info('Automatic data trasfer to data analysis computer is enabled.')
            full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
            remote_analysis_dir = self.epics_pvs['RemoteAnalysisDir'].get(as_string=True)
            dm.scp(full_file_name, remote_analysis_dir)
        else:
            log.warning('Automatic data trasfer to data analysis computer is disabled.')
           
      
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

        self.epics_pvs['MoveSampleIn'].put('Done')

    def move_sample_out(self):
        """Moves the sample to the out of beam position for collecting flat fields.

        The out of beam position is defined by the ``SampleOutX`` and ``SampleOutY`` PVs.

        Which axis to move is defined by the ``FlatFieldAxis`` PV,
        which can be ``X``, ``Y``, or ``Both``.
        """

        axis = self.epics_pvs['FlatFieldAxis'].get(as_string=True)
        log.info('move_sample_out axis: %s', axis)
        if axis in ('X', 'Both'):
            position = self.epics_pvs['SampleOutX'].value
            self.epics_pvs['SampleX'].put(position, wait=True, timeout=600)

        if axis in ('Y', 'Both'):
            position = self.epics_pvs['SampleOutY'].value
            self.epics_pvs['SampleY'].put(position, wait=True, timeout=600)

        self.epics_pvs['MoveSampleOut'].put('Done')

