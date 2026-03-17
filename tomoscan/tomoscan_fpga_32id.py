"""Software for tomography scanning with EPICS at APS beamline 32-ID using FPGA triggers

   Classes
   -------
   TomoScanFPGA32ID
     Derived class for tomography scanning with EPICS at APS beamline 32-ID
     using the softGlueZynq FPGA for interlaced trigger generation.
     Inherits from TomoScanFPGAPSO (PSO + FPGA interlaced logic) and adds
     all 32-ID beamline-specific hardware: front-end shutter, fast shutter,
     energy change via TXMOptics, and microCT data collection.
"""
import time
import os
import h5py
import sys
import traceback
import numpy as np
import pvaccess as pva
import threading
from epics import PV
from pathlib import Path

from tomoscan import data_management as dm
from tomoscan.tomoscan_fpga_pso import TomoScanFPGAPSO
from tomoscan import log

EPSILON = .001


class TomoScanFPGA32ID(TomoScanFPGAPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 32-ID
    using the softGlueZynq FPGA for interlaced trigger generation.

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

        # Set TomoScan xml files
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

        # TXMOptics PVs
        prefix = self.pv_prefixes['TxmOptics']
        self.epics_pvs['TXMEnergySet']  = PV(prefix + 'EnergySet')
        self.epics_pvs['TXMEnergy']     = PV(prefix + 'Energy')
        self.epics_pvs['TXMMoveAllOut'] = PV(prefix + 'MoveAllOut')
        self.epics_pvs['TXMMoveAllIn']  = PV(prefix + 'MoveAllIn')

        # PVA channel that contains projection image and metadata
        prefix = self.pv_prefixes['Image']
        self.epics_pvs['PvaPImage']        = pva.Channel(prefix + 'Image')
        self.epics_pvs['PvaPDataType_RBV'] = pva.Channel(prefix + 'DataType_RBV')

        # Energy change callback
        self.epics_pvs['EnergySet'].put(0)
        self.epics_pvs['EnergySet'].add_callback(self.pv_callback_32id)

        # Sample SET field PVs (needed to zero the dial position)
        self.epics_pvs['SampleXSet'] = PV(self.control_pvs['SampleX'].pvname + '.SET')
        self.epics_pvs['SampleYSet'] = PV(self.control_pvs['SampleY'].pvname + '.SET')

        log.setup_custom_logger("./tomoscan.log")

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def pv_callback_32id(self, pvname=None, value=None, char_value=None, **kw):
        """Callback function that is called by pyEpics when certain EPICS PVs are changed."""
        log.debug('pv_callback_32id pvName=%s, value=%s, char_value=%s', pvname, value, char_value)
        if (pvname.find('EnergySet') != -1) and value == 1:
            thread = threading.Thread(target=self.energy_change, args=())
            thread.start()

    # ------------------------------------------------------------------
    # Shutter control
    # ------------------------------------------------------------------

    def open_frontend_shutter(self):
        """Opens the front-end shutter to allow beam into the beamline.

        In testing mode this is skipped.  Otherwise opens the 32-ID
        front-end shutter and waits until it reports open.
        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
        else:
            if not self.epics_pvs['OpenShutter'] is None:
                pv    = self.epics_pvs['OpenShutter']
                value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)
                log.info('open shutter: %s, value: %s', pv, value)
                self.epics_pvs['OpenShutter'].put(value, wait=True)
                self.wait_frontend_shutter_open()
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)

    def open_shutter(self):
        """Opens the 32-ID-C Uniblitz fast shutter."""
        if not self.epics_pvs['OpenFastShutter'] is None:
            pv    = self.epics_pvs['OpenFastShutter']
            value = self.epics_pvs['OpenFastShutterValue'].get(as_string=True)
            log.info('open fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenFastShutter'].put(value, wait=True)

    def close_frontend_shutter(self):
        """Closes the 32-ID front-end shutter.

        In testing mode this is skipped.
        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
        else:
            if not self.epics_pvs['CloseShutter'] is None:
                pv    = self.epics_pvs['CloseShutter']
                value = self.epics_pvs['CloseShutterValue'].get(as_string=True)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)
                log.info('close shutter: %s, value: %s', pv, value)
                self.epics_pvs['CloseShutter'].put(value, wait=True)
                self.wait_pv(self.epics_pvs['ShutterStatus'], 0)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)

    def close_shutter(self):
        """Closes the 32-ID-C Uniblitz fast shutter."""
        if not self.epics_pvs['CloseFastShutter'] is None:
            pv    = self.epics_pvs['CloseFastShutter']
            value = self.epics_pvs['CloseFastShutterValue'].get(as_string=True)
            log.info('close fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseFastShutter'].put(value, wait=True)

    # ------------------------------------------------------------------
    # Trigger mode
    # ------------------------------------------------------------------

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode for the camera.

        Dispatches to the camera-model-specific method.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"
        num_images : int
            Number of images to collect.  Ignored for "FreeRun".
        """
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        if camera_model in ('Oryx ORX-10G-51S5M', 'Oryx ORX-10G-310S9M'):
            self.set_trigger_mode_oryx(trigger_mode, num_images)
        elif camera_model in ('Grasshopper3 GS3-U3-51S5M', 'Blackfly S BFS-PGE-161S7M'):
            self.set_trigger_mode_grasshopper(trigger_mode, num_images)
        else:
            log.error('Camera model not supported: %s', camera_model)
            exit(1)

    def set_trigger_mode_oryx(self, trigger_mode, num_images):
        self.epics_pvs['CamAcquire'].put('Done')
        self.wait_pv(self.epics_pvs['CamAcquire'], 0)
        log.info('set trigger mode: %s', trigger_mode)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else:  # PSOExternal
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

    def set_trigger_mode_grasshopper(self, trigger_mode, num_images):
        self.epics_pvs['CamAcquire'].put('Done')
        self.wait_pv(self.epics_pvs['CamAcquire'], 0)
        log.info('set trigger mode: %s', trigger_mode)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else:  # PSOExternal
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.epics_pvs['CamTriggerSource'].put('Line2', wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateEnable'].put(0)
            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 1)

    # ------------------------------------------------------------------
    # Scan lifecycle
    # ------------------------------------------------------------------

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Handles Pause state if the scan was paused.

        - Resets sample X/Y dial position to zero.

        - Sets the data directory path from experiment metadata PVs.

        - Calls the base class method (TomoScanFPGAPSO.begin_scan) which
          programs the FPGA/PSO and starts the camera.

        - Opens the front-end shutter.
        """
        pause = self.epics_pvs['Pause'].get(as_string=True)
        if pause == 'PAUSE':
            log.warning('scan is paused')
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamAcquire'].put('Acquire')
            self.epics_pvs['HDF5Location'].put('/exchange/Pause')
            self.epics_pvs['ScanStatus'].put('Pause')
            log.warning('open fast shutter')
            self.open_shutter()
            while True:
                pause = self.epics_pvs['Pause'].get(as_string=True)
                if pause == 'GO':
                    break
                time.sleep(0.2)

        log.info('begin scan')

        # Zero the sample dial position
        self.epics_pvs['SampleXSet'].put(1, wait=True)
        self.epics_pvs['SampleYSet'].put(1, wait=True)
        self.epics_pvs['SampleX'].put(0, wait=True)
        self.epics_pvs['SampleY'].put(0, wait=True)
        self.epics_pvs['SampleXSet'].put(0, wait=True)
        self.epics_pvs['SampleYSet'].put(0, wait=True)

        # Set data directory
        file_path = Path(self.epics_pvs['DetectorTopDir'].get(as_string=True))
        file_path = file_path.joinpath(
            self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + '-'
            + self.epics_pvs['UserLastName'].get(as_string=True) + '-'
            + self.epics_pvs['ProposalNumber'].get(as_string=True))
        self.epics_pvs['FilePath'].put(str(file_path), wait=True)

        # Call base class method (programs FPGA/PSO, sets exposure, starts HDF capture)
        super().begin_scan()

        # Open the front-end shutter
        self.open_frontend_shutter()

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - If ReturnRotation is Yes, resets the rotation dial position mod 360.

        - Stops the file plugin.

        - Writes theta angles into the HDF5 data file.

        - Optionally collects a microCT projection via PVA.

        - Closes the fast shutter.

        - Optionally copies data to the remote analysis computer.

        - Calls the base class method (TomoScanFPGAPSO.end_scan).
        """
        if self.return_rotation == 'Yes':
            log.info('wait until the stage is stopped')
            time.sleep(self.epics_pvs['RotationAccelTime'].get() * 1.2)
            ang = self.epics_pvs['RotationRBV'].get()
            current_angle = np.sign(ang) * (np.abs(ang) % 360)
            self.epics_pvs['RotationSet'].put('Set', wait=True)
            self.epics_pvs['Rotation'].put(current_angle, wait=True)
            self.epics_pvs['RotationSet'].put('Use', wait=True)

        # Stop the file plugin
        self.epics_pvs['FPCapture'].put('Done')
        self.wait_pv(self.epics_pvs['FPCaptureRBV'], 0)

        # Write theta into the HDF5 file
        self.add_theta()

        # Optionally collect a microCT projection
        if self.epics_pvs['CollectMicroCTdata'].get(as_string=True) == 'Yes':
            try:
                log.warning('take microCT projection')
                self.epics_pvs['TXMMoveAllOut'].put(1, wait=True)
                self.epics_pvs['CamAcquire'].put(1)
                log.info('write to %s', self.epics_pvs['FPFullFileName'].get(as_string=True))
                time.sleep(0.5)
                with h5py.File(self.epics_pvs['FPFullFileName'].get(as_string=True), 'r+') as fid:
                    pva_image_data = self.epics_pvs['PvaPImage'].get('')
                    width  = pva_image_data['dimension'][0]['size']
                    height = pva_image_data['dimension'][1]['size']
                    datatype_list = self.epics_pvs['PvaPDataType_RBV'].get()['value']
                    type_dict = {
                        'uint8':   'ubyteValue',
                        'float32': 'floatValue',
                        'uint16':  'ushortValue',
                    }
                    datatype = type_dict[datatype_list['choices'][datatype_list['index']].lower()]
                    data = pva_image_data['value'][0][datatype]
                    fid.create_dataset('exchange/data2', data=data.reshape([height, width]))
                self.epics_pvs['CamAcquire'].put(0)
            except Exception:
                log.warning('microCT projection was not taken')

        # Close the fast shutter
        self.close_shutter()

        # Optionally copy data to the remote analysis computer
        full_file_name      = self.epics_pvs['FPFullFileName'].get(as_string=True)
        remote_analysis_dir = self.epics_pvs['RemoteAnalysisDir'].get(as_string=True)
        copy_to_analysis_dir = self.epics_pvs['CopyToAnalysisDir'].get()
        if copy_to_analysis_dir == 1:
            log.info('Using FDT')
            dm.fdt_scp(full_file_name, remote_analysis_dir,
                       Path(self.epics_pvs['DetectorTopDir'].get()))
            self.epics_pvs['ScanStatus'].put('fdt file transfer complete')
        elif copy_to_analysis_dir == 2:
            log.info('Using scp')
            dm.scp(full_file_name, remote_analysis_dir)
            self.epics_pvs['ScanStatus'].put('scp file transfer complete')
        else:
            log.warning('Automatic data transfer to data analysis computer is disabled.')

        # Call base class method (saves config, sets FreeRun, resets MUX, moves sample in)
        super().end_scan()

    # ------------------------------------------------------------------
    # Energy change
    # ------------------------------------------------------------------

    def energy_change(self):
        """Change energy through TXMOptics."""
        energy = self.epics_pvs['Energy'].get()
        self.epics_pvs['TXMEnergy'].put(energy, wait=True)
        self.epics_pvs['TXMEnergySet'].put(1, wait=True)
        time.sleep(1)
        self.epics_pvs['EnergySet'].put(0)

    # ------------------------------------------------------------------
    # Theta / HDF5
    # ------------------------------------------------------------------

    def add_theta(self):
        """Write theta angles into the HDF5 data file and log any missing frames."""
        log.info('add theta')
        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        if os.path.exists(full_file_name):
            try:
                with h5py.File(full_file_name, 'a') as f:
                    if self.theta is not None:
                        unique_ids   = f['/defaults/NDArrayUniqueId']
                        hdf_location = f['/defaults/HDF5FrameLocation']
                        total_dark_fields = self.num_dark_fields * (
                            (self.dark_field_mode in ('Start', 'Both'))
                            + (self.dark_field_mode in ('End', 'Both')))
                        total_flat_fields = self.num_flat_fields * (
                            (self.flat_field_mode in ('Start', 'Both'))
                            + (self.flat_field_mode in ('End', 'Both')))

                        proj_ids = unique_ids[hdf_location[:] == b'/exchange/data']
                        flat_ids = unique_ids[hdf_location[:] == b'/exchange/data_white']
                        dark_ids = unique_ids[hdf_location[:] == b'/exchange/data_dark']

                        if len(proj_ids) > 0:
                            theta_ds = f.create_dataset('/exchange/theta', (len(proj_ids),))
                            theta_ds[:] = self.theta[proj_ids - proj_ids[0]]

                        if len(proj_ids) != len(self.theta):
                            log.warning('There are %d missing data frames (expected %d, recorded %d)',
                                        len(self.theta) - len(proj_ids),
                                        len(self.theta), len(proj_ids))
                            if len(proj_ids) > 0:
                                missed_ids   = [i for i in range(len(self.theta))
                                                if i not in proj_ids - proj_ids[0]]
                                missed_theta = self.theta[missed_ids]
                                log.warning('Missed theta (first 50): %s', list(missed_theta[:50]))
                        if len(flat_ids) != total_flat_fields:
                            log.warning('There are %d missing flat field frames',
                                        total_flat_fields - len(flat_ids))
                        if len(dark_ids) != total_dark_fields:
                            log.warning('There are %d missing dark field frames',
                                        total_dark_fields - len(dark_ids))
            except Exception:
                log.error('Add theta: Failed accessing: %s', full_file_name)
                traceback.print_exc(file=sys.stdout)
        else:
            log.error('Failed adding theta. %s file does not exist', full_file_name)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def wait_pv(self, epics_pv, wait_val, timeout=-1):
        """Wait for an EPICS PV to reach wait_val (default: wait forever)."""
        time.sleep(.01)
        start_time = time.time()
        while True:
            pv_val = epics_pv.get()
            if isinstance(pv_val, float):
                if abs(pv_val - wait_val) < EPSILON:
                    return True
            if pv_val != wait_val:
                if timeout > -1:
                    if time.time() - start_time >= timeout:
                        log.error('wait_pv(%s, %d, %5.2f) reached max timeout. Return False',
                                  epics_pv.pvname, wait_val, timeout)
                        return False
                time.sleep(.01)
            else:
                return True

    def wait_frontend_shutter_open(self, timeout=-1):
        """Wait for the front-end shutter to open, retrying periodically.

        Parameters
        ----------
        timeout : float
            Maximum seconds to wait; -1 means wait forever.
        """
        start_time = time.time()
        pv    = self.epics_pvs['OpenShutter']
        value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
        log.info('open shutter: %s, value: %s', pv, value)
        elapsed_time = 0
        while True:
            if self.epics_pvs['ShutterStatus'].get() == int(value):
                log.warning('Shutter is open in %f s', elapsed_time)
                return
            if not self.scan_is_running:
                exit()
            value = self.epics_pvs['OpenShutterValue'].get()
            time.sleep(1.0)
            elapsed_time = time.time() - start_time
            log.warning('Waiting on shutter to open: %f s', elapsed_time)
            self.epics_pvs['OpenShutter'].put(value, wait=True)
            if timeout > 0:
                if elapsed_time >= timeout:
                    exit()
