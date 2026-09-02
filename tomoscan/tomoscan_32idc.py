"""Software for tomography scanning with EPICS at APS beamline 32-ID-C

   Classes
   -------
   TomoScan32IDC
     Derived class for tomography scanning with EPICS at APS beamline 32-ID-C
"""
import os
import sys
import time
import pathlib
import traceback
import threading
import urllib.request

import h5py
import numpy as np

from epics import PV
from pathlib import Path

from tomoscan import data_management as dm
from tomoscan.tomoscan_pso import TomoScanPSO
from tomoscan import log

EPSILON = .001

CREDENTIALS_FILE_NAME = os.path.join(str(pathlib.Path.home()), '.webcam_credentials')

# Panasonic IP camera looking at the 32-ID-C Micro-CT stage.  Note that the
# obvious /cgi-bin/jpeg endpoint returns 403 for this camera; /cgi-bin/camera
# is the one that serves a single JPEG snapshot.  The camera uses HTTP Digest
# authentication, so a plain user:pass@host URL does not work either.
WEBCAM_URL = 'http://remotecam32idch.xray.aps.anl.gov/cgi-bin/camera'
WEBCAM_TIMEOUT = 10.0

# Sensor readout time in seconds for the Teledyne Photometrics Kinetix.
#
# Unlike the FLIR/Adimec cameras handled by TomoScan.compute_frame_time(), the
# Kinetix has no GenICam PixelFormat record to key a readout table off; its
# readout time is set by the selected readout port / speed table.  This value
# is deliberately conservative: too long only makes the scan slower, too short
# drops frames.  See compute_frame_time() below -- if the driver publishes a
# readout time it is used in preference to this constant.
KINETIX_READOUT_TIME = 0.010
KINETIX_READOUT_MARGIN = 1.05


class TomoScan32IDC(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 32-ID-C

    The 32-ID-C Micro-CT station is architecturally closer to 2-BM than to the
    32-ID-B TXM: it uses the mctoptics optics server rather than TXMOptics, so
    this class follows tomoscan_2bm rather than tomoscan_32id for the optics and
    areaDetector plugin wiring.  It differs from tomoscan_2bm in three ways:

    - There is no fast shutter.  Beam is admitted to the C station by the 32-ID-B
      shutter; the 32-ID-A shutter is left open permanently.  open_shutter() and
      close_shutter() are therefore no-ops and no fast shutter PVs are defined.
    - There is no PDU, so no ~/access.json is read.
    - The web camera frame is grabbed with urllib + Pillow rather than OpenCV.

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

        prefix = self.pv_prefixes['MctOptics']
        self.epics_pvs['ImagePixelSize'] = PV(prefix + 'ImagePixelSize')

        # Set TomoScan xml files.  These are the mct* files used by the 32-ID
        # Kinetix IOC, not the TomoScan* files used at 2-BM.
        self.epics_pvs['CamNDAttributesFile'].put('mctDetectorAttributes.xml')
        self.epics_pvs['FPXMLFileName'].put('mctLayout.xml')
        macro = ('DET=' + self.pv_prefixes['Camera'] + ',' + 'TS='
                 + self.epics_pvs['Testing'].__dict__['pvname'].replace('Testing', '', 1))
        self.control_pvs['CamNDAttributesMacros'].put(macro)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Disable over writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

        log.setup_custom_logger("./tomoscan.log")

        # Set AD plugins
        self.epics_pvs['PVANDArrayPort'].put('OVER1')
        self.epics_pvs['PVAEnableCallbacks'].put('Enable')
        self.epics_pvs['ROIEnableCallbacks'].put('Disable')
        self.epics_pvs['CBEnableCallbacks'].put('Disable')

        # Configure callbacks for mctoptics
        prefix = self.pv_prefixes['MctOptics']
        self.epics_pvs['CameraSelect'] = PV(prefix + 'CameraSelect')
        camera_select = self.epics_pvs['CameraSelect'].value
        if camera_select == None:
            log.error('mctOptics is down. Please start mctOptics first')
        else:
            self.epics_pvs['Camera0']     = PV(prefix + 'Camera0PVPrefix')
            self.epics_pvs['Camera1']     = PV(prefix + 'Camera1PVPrefix')
            self.epics_pvs['FilePlugin0'] = PV(prefix + 'FilePlugin0PVPrefix')
            self.epics_pvs['FilePlugin1'] = PV(prefix + 'FilePlugin1PVPrefix')
            self.epics_pvs['PvaPlugin1']  = PV(prefix + 'PvaPlugin1PVPrefix')
            self.epics_pvs['RoiPlugin0']  = PV(prefix + 'RoiPlugin0PVPrefix')
            self.epics_pvs['RoiPlugin1']  = PV(prefix + 'RoiPlugin1PVPrefix')
            self.epics_pvs['CbPlugin0']   = PV(prefix + 'CbPlugin0PVPrefix')
            self.epics_pvs['CbPlugin1']   = PV(prefix + 'CbPlugin1PVPrefix')

            self.epics_pvs['CameraSelect'].add_callback(self.pv_callback_32idc)

    def pv_callback_32idc(self, pvname=None, value=None, char_value=None, **kw):
        """Callback function that is called by pyEpics when certain EPICS PVs are changed
        """
        log.debug('pv_callback_32idc pvName=%s, value=%s, char_value=%s', pvname, value, char_value)
        if (pvname.find('CameraSelect') != -1):
            thread = threading.Thread(target=self.reinit_camera, args=())
            thread.start()

    def reinit_camera(self):
        """Init camera PVs based on the mctOptics selection.
        """
        if not self.scan_is_running:
            prefix = self.pv_prefixes['MctOptics']
            self.epics_pvs['CameraSelect'] = PV(prefix + 'CameraSelect')
            camera_select = self.epics_pvs['CameraSelect'].value
            log.info('changing camera prefix to camera %s', camera_select)

            if camera_select == None:
                log.error('mctOptics is down. Please start mctOptics first')
                return

            self.epics_pvs['Camera0']     = PV(prefix + 'Camera0PVPrefix')
            self.epics_pvs['Camera1']     = PV(prefix + 'Camera1PVPrefix')
            self.epics_pvs['FilePlugin0'] = PV(prefix + 'FilePlugin0PVPrefix')
            self.epics_pvs['FilePlugin1'] = PV(prefix + 'FilePlugin1PVPrefix')
            self.epics_pvs['PvaPlugin0']  = PV(prefix + 'PvaPlugin0PVPrefix')
            self.epics_pvs['PvaPlugin1']  = PV(prefix + 'PvaPlugin1PVPrefix')
            self.epics_pvs['RoiPlugin0']  = PV(prefix + 'RoiPlugin0PVPrefix')
            self.epics_pvs['RoiPlugin1']  = PV(prefix + 'RoiPlugin1PVPrefix')
            self.epics_pvs['CbPlugin0']   = PV(prefix + 'CbPlugin0PVPrefix')
            self.epics_pvs['CbPlugin1']   = PV(prefix + 'CbPlugin1PVPrefix')

            if camera_select == 0:
                camera_prefix = self.epics_pvs['Camera0'].get(as_string=True)
                hdf_prefix    = self.epics_pvs['FilePlugin0'].get(as_string=True)
                pva_prefix    = self.epics_pvs['PvaPlugin0'].get(as_string=True)
                roi_prefix    = self.epics_pvs['RoiPlugin0'].get(as_string=True)
                cb_prefix     = self.epics_pvs['CbPlugin0'].get(as_string=True)
            else:
                camera_prefix = self.epics_pvs['Camera1'].get(as_string=True)
                hdf_prefix    = self.epics_pvs['FilePlugin1'].get(as_string=True)
                pva_prefix    = self.epics_pvs['PvaPlugin1'].get(as_string=True)
                roi_prefix    = self.epics_pvs['RoiPlugin1'].get(as_string=True)
                cb_prefix     = self.epics_pvs['CbPlugin1'].get(as_string=True)

            self.epics_pvs['CameraPVPrefix'].put(camera_prefix, wait=True)
            self.epics_pvs['FilePluginPVPrefix'].put(hdf_prefix, wait=True)
            self.epics_pvs['PvaPluginPVPrefix'].put(pva_prefix)
            self.epics_pvs['RoiPluginPVPrefix'].put(roi_prefix)
            self.epics_pvs['CbPluginPVPrefix'].put(cb_prefix)
            log.info('camera %s, hdf %s, pva %s, roi %s, cb %s',
                     camera_prefix, hdf_prefix, pva_prefix, roi_prefix, cb_prefix)

            self.pv_prefixes['FilePlugin'] = hdf_prefix

            # Update the camera PVs
            camera_prefix = camera_prefix + 'cam1:'
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

            prefix = hdf_prefix
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
            self.control_pvs['FPWriteStatus']     = PV(prefix + 'WriteStatus')

            # Set some initial PV values
            file_path = self.config_pvs['FilePath'].get(as_string=True)
            self.control_pvs['FPFilePath'].put(file_path)
            file_name = self.config_pvs['FileName'].get(as_string=True)
            self.control_pvs['FPFileName'].put(file_name)
            self.control_pvs['FPAutoSave'].put('No')
            self.control_pvs['FPFileWriteMode'].put('Stream')
            self.control_pvs['FPEnableCallbacks'].put('Enable')

            prefix = pva_prefix
            self.control_pvs['PVANDArrayPort']     = PV(prefix + 'NDArrayPort')
            self.control_pvs['PVAEnableCallbacks'] = PV(prefix + 'EnableCallbacks')
            self.control_pvs['PVANDArrayPort'].put('OVER1')
            self.control_pvs['PVAEnableCallbacks'].put('Enable')

            prefix = roi_prefix
            self.control_pvs['ROINDArrayPort']     = PV(prefix + 'NDArrayPort')
            self.control_pvs['ROIScale']           = PV(prefix + 'Scale')
            self.control_pvs['ROIBinX']            = PV(prefix + 'BinX')
            self.control_pvs['ROIBinY']            = PV(prefix + 'BinY')
            self.control_pvs['ROIEnableCallbacks'] = PV(prefix + 'EnableCallbacks')
            self.control_pvs['ROIEnableCallbacks'].put('Disable')

            prefix = cb_prefix
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
            self.control_pvs['CBEnableCallbacks'].put('Disable')

            self.epics_pvs = {**self.config_pvs, **self.control_pvs}
            # Wait 1 second for all PVs to connect
            time.sleep(1)
            self.check_pvs_connected()

    def open_frontend_shutter(self):
        """Opens the shutter to collect flat fields or projections.

        Beam is admitted to the 32-ID-C station by the 32-ID-B shutter; the
        32-ID-A shutter is left open permanently.  This is the same logic used
        by tomoscan_32id, whose ShutterStatus PV also has "1 == open"
        semantics (PA:32ID:STA_?_SBS_OPEN_PL).
        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
        else:
            if not self.epics_pvs['OpenShutter'] is None:
                pv = self.epics_pvs['OpenShutter']
                value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)
                log.info('open shutter: %s, value: %s', pv, value)
                self.epics_pvs['OpenShutter'].put(value, wait=True)
                self.wait_frontend_shutter_open()
                status = self.epics_pvs['ShutterStatus'].get(as_string=True)
                log.info('shutter status: %s', status)

    def close_frontend_shutter(self):
        """Closes the shutter to collect dark fields."""
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not closing shutters.')
        else:
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

    def open_shutter(self):
        """No-op: the 32-ID-C Micro-CT station has no fast shutter."""
        log.info('no fast shutter at 32-ID-C, nothing to open')

    def close_shutter(self):
        """No-op: the 32-ID-C Micro-CT station has no fast shutter."""
        log.info('no fast shutter at 32-ID-C, nothing to close')

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode of the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
        """
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        if camera_model == 'Kinetix':
            self.set_trigger_mode_kinetix(trigger_mode, num_images)
        else:
            log.error('Camera %s is not supported', camera_model)
            exit(1)

    def set_trigger_mode_kinetix(self, trigger_mode, num_images):
        """Sets the trigger mode for the Teledyne Photometrics Kinetix (ADKinetix).

        ADKinetix is not a GenICam driver: it has no TriggerSource,
        TriggerOverlap, ExposureMode or FrameRateEnable records, so only
        ImageMode / TriggerMode / NumImages are touched here.  The TriggerMode
        choices are "Internal", "Rising Edge" and "Exp. Gate"; the PSO output
        drives the camera through "Rising Edge".
        """
        self.epics_pvs['CamAcquire'].put('Done')
        self.wait_pv(self.epics_pvs['CamAcquire'], 0)
        log.info('set trigger mode: %s', trigger_mode)
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Internal', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
        elif trigger_mode == 'Internal':
            self.epics_pvs['CamTriggerMode'].put('Internal', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 0)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
        else:  # external triggering from the PSO output
            self.epics_pvs['CamTriggerMode'].put('Internal', wait=True)
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(self.num_angles, wait=True)
            self.epics_pvs['CamTriggerMode'].put('Rising Edge', wait=True)
            self.wait_pv(self.epics_pvs['CamTriggerMode'], 1)

    def compute_frame_time(self):
        """Computes the time to collect and read out an image from the Kinetix.

        TomoScan.compute_frame_time() keys its readout table off the GenICam
        ``PixelFormat`` record, which ADKinetix does not have -- on this camera
        the base class raises UnboundLocalError before it can even report the
        unsupported model.  The base class docstring directs single-beamline
        cameras to override here, which is what this does.

        Any camera other than the Kinetix is handed back to the base class, so
        that selecting a different detector through mctOptics still works.
        """
        camera_model = self.epics_pvs['CamModel'].get(as_string=True)
        if camera_model != 'Kinetix':
            return super().compute_frame_time()

        # Prefer a readout time published by the driver, if this version of
        # ADKinetix provides one; otherwise fall back to the conservative
        # constant above.
        readout = None
        readout_pv = self.epics_pvs.get('CamReadoutTimeRBV')
        if readout_pv is not None and readout_pv.connected:
            value = readout_pv.get()
            if value:
                # ADKinetix reports the readout time in microseconds
                readout = value / 1.e6
        if readout is None:
            readout = KINETIX_READOUT_TIME
            log.warning('Kinetix readout time not published by the driver; '
                        'using the conservative default of %.1f ms. Reduce '
                        'KINETIX_READOUT_TIME in tomoscan_32idc.py once the '
                        'readout time has been measured for the readout mode '
                        'in use.', readout * 1000.)

        exposure = self.epics_pvs['CamAcquireTimeRBV'].value
        frame_time = exposure * KINETIX_READOUT_MARGIN
        if frame_time < readout:
            frame_time = readout + .001
        self.readout_margin = KINETIX_READOUT_MARGIN
        return frame_time

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Sets the data directory.

        - Calls the base class method.

        - Opens the front-end shutter.
        """
        log.info('begin scan')

        # Set data directory
        file_path = Path(self.epics_pvs['DetectorTopDir'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + '-'
                                       + self.epics_pvs['UserLastName'].get(as_string=True) + '-'
                                       + self.epics_pvs['ProposalNumber'].get(as_string=True))
        self.epics_pvs['FilePath'].put(str(file_path), wait=True)

        # Call the base class method
        super().begin_scan()

        # Open the front-end shutter
        self.open_frontend_shutter()

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Resets the rotation position by mod 360.

        - Stops the file plugin.

        - Adds theta to the raw data file.

        - Adds a web camera frame to the raw data file.

        - Copies the raw data to the data analysis computer.

        - Calls the base class method.
        """
        if self.return_rotation == 'Yes':
            # Reset rotation position by mod 360, the actual return
            # to start position is handled by super().end_scan()
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

        # Add theta in the hdf file
        self.add_theta()

        # Add a web camera frame in the hdf file
        self.add_web_camera_frame()

        # Copy raw data to data analysis computer
        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        remote_analysis_dir = self.epics_pvs['RemoteAnalysisDir'].get(as_string=True)
        copy_to_analysis_dir = self.epics_pvs['CopyToAnalysisDir'].get()
        if copy_to_analysis_dir == 1:
            log.info('Using FDT')
            dm.fdt_scp(full_file_name, remote_analysis_dir,
                       Path(self.epics_pvs['DetectorTopDir'].get()))
            self.epics_pvs['ScanStatus'].put('fdt file transfer complete')
        elif copy_to_analysis_dir == 2:
            log.info('Using scp')
            dm.scp(full_file_name, remote_analysis_dir,
                   Path(self.epics_pvs['DetectorTopDir'].get()))
            self.epics_pvs['ScanStatus'].put('scp file transfer complete')
        else:
            log.warning('Automatic data transfer to data analysis computer is disabled.')

        # Call the base class method
        super().end_scan()

    def read_webcam_credentials(self):
        """Reads the web camera username and password.

        The credentials live in ~/.webcam_credentials as a single
        ``username|password`` line.  They are deliberately kept out of the
        source tree because this repository is public.

        Returns
        -------
        tuple of (str, str), or (None, None) if the file cannot be read.
        """
        try:
            with open(CREDENTIALS_FILE_NAME, 'r') as fp:
                for line in fp:
                    line = line.strip()
                    if line:
                        username, password = line.split('|')
                        return username, password
        except Exception:
            log.warning('Cannot read web camera credentials from %s', CREDENTIALS_FILE_NAME)
        return None, None

    def grab_webcam_frame(self):
        """Grabs a single frame from the 32-ID-C web camera.

        The camera uses HTTP Digest authentication, so the credentials cannot
        simply be embedded in the URL.  Pillow is used to decode the JPEG;
        OpenCV is deliberately not used because it is not installed in the
        tomoscan environment and cannot do Digest authentication anyway.

        Returns
        -------
        numpy.ndarray of shape (height, width, 3), or None on any failure.
        """
        username, password = self.read_webcam_credentials()
        if username is None:
            return None

        from PIL import Image
        import io

        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, WEBCAM_URL, username, password)
        opener = urllib.request.build_opener(
            urllib.request.HTTPDigestAuthHandler(password_mgr),
            urllib.request.HTTPBasicAuthHandler(password_mgr))
        with opener.open(WEBCAM_URL, timeout=WEBCAM_TIMEOUT) as response:
            payload = response.read()
        return np.asarray(Image.open(io.BytesIO(payload)).convert('RGB'))

    def add_web_camera_frame(self):
        """Adds a frame from the web camera to the raw data file.

        A failure here must never fail the scan, so everything is wrapped.
        """
        log.info('Adding a frame from the IP camera')
        try:
            frame = self.grab_webcam_frame()
            if frame is None:
                log.warning('The web camera frame was not added')
                return
            full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
            with h5py.File(full_file_name, 'r+') as fid:
                fid.create_dataset('exchange/web_camera_frame', data=frame)
            log.info('The web camera frame was added')
        except Exception:
            log.warning('The web camera frame was not added')
            traceback.print_exc(file=sys.stdout)

    def add_theta(self):
        """Add theta at the end of a scan."""
        log.info('add theta')

        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        if not os.path.exists(full_file_name):
            log.error('Failed adding theta. %s file does not exist', full_file_name)
            return
        try:
            with h5py.File(full_file_name, "a") as f:
                if self.theta is not None:
                    unique_ids = f['/defaults/NDArrayUniqueId']
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

                    # create theta dataset in hdf5 file
                    if len(proj_ids) > 0:
                        theta_ds = f.create_dataset('/exchange/theta', (len(proj_ids),))
                        theta_ds[:] = self.theta[proj_ids - proj_ids[0]]

                    # warnings that data is missing
                    if len(proj_ids) != len(self.theta):
                        log.warning('There are %d missing data frames',
                                    len(self.theta) - len(proj_ids))
                        missed_ids = [ele for ele in range(len(self.theta))
                                      if ele not in proj_ids - proj_ids[0]]
                        missed_theta = self.theta[missed_ids]
                        log.warning('Missed theta: %s', list(missed_theta))
                    if len(flat_ids) != total_flat_fields:
                        log.warning('There are %d missing flat field frames',
                                    total_flat_fields - len(flat_ids))
                    if len(dark_ids) != total_dark_fields:
                        log.warning('There are %d missing dark field frames',
                                    total_dark_fields - len(dark_ids))
        except Exception:
            log.error('Add theta: Failed accessing: %s', full_file_name)
            traceback.print_exc(file=sys.stdout)

    def wait_pv(self, epics_pv, wait_val, timeout=-1):
        """Wait on a pv to be a value until max_timeout (default forever)"""
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

        While waiting this method periodically tries to open the shutter.

        Parameters
        ----------
        timeout : float
            The maximum number of seconds to wait before giving up.
        """
        start_time = time.time()
        pv = self.epics_pvs['OpenShutter']
        value = self.epics_pvs['OpenShutterValue'].get(as_string=True)
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
