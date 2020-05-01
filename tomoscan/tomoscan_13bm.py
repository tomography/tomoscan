"""Software for tomography scanning with EPICS at APS beamline 13-BM-D

   Classes
   -------
   TomoScan13BM
     Derived class for tomography scanning with EPICS at APS beamline 13-BM-D
"""
import time
import math
from tomoscan import TomoScan

class TomoScan13BM(TomoScan):
    """Derived class used for tomography scanning with EPICS at APS beamline 13-BM-D

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
        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')
        # Set the SIS output pulse width to 100 us
        self.epics_pvs['MCSLNEOutputWidth'].put(0.0001)

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode SIS3820 and the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "MCSInternal", or "MCSExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
            This is used to set the ``NuseAll`` PV of the SIS MCS,
            the ``NumImages`` PV of the camera, and the ``NumCapture``
            PV of the file plugin.
        """
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.epics_pvs['CamAcquire'].put('Acquire')
        else: # set camera to external triggering
            self.epics_pvs['CamImageMode'].put('Multiple', wait=True)
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            # Set number of MCS channels, NumImages, and NumCapture
            self.epics_pvs['MCSStopAll'].put(1, wait=True)
            self.epics_pvs['MCSNuseAll'].put(num_images, wait=True)
            self.epics_pvs['FPNumCapture'].put(num_images, wait=True)

        if trigger_mode == 'MCSExternal':
            # Put MCS in external trigger mode
            self.epics_pvs['MCSChannelAdvance'].put('External', wait=True)

        if trigger_mode == 'MCSInternal':
            self.epics_pvs['MCSChannelAdvance'].put('Internal', wait=True)
            frame_time = self.compute_frame_time()
            self.epics_pvs['MCSDwell'].put(frame_time, wait=True)

    def collect_static_frames(self, num_frames, save=True):
        """Collects num_frames images in "MCSInternal" trigger mode for dark fields and flat fields.

        Parameters
        ----------
        num_frames : int
            Number of frames to collect.

        save : bool, optional
            False to disable saving frames with the file plugin.
        """
        # This is called when collecting dark fields or flat fields
        self.set_trigger_mode('MCSInternal', num_frames)
        if save:
            self.epics_pvs['FPCapture'].put('Capture')
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Wait for detector and file plugin to be ready
        time.sleep(0.5)
        # Start the MCS
        self.epics_pvs['MCSEraseStart'].put(1)
        collection_time = self.epics_pvs['MCSDwell'].value * num_frames
        self.wait_camera_done(collection_time + 5.0)

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Calls the base class method.

        - Collects 3 dummy images with ``collect_static_frames``.
          This is required when switching from "FreeRun" to triggered mode
          on the Point Grey camera.

        - Sets the FileNumber back to 1 because we collect dark-fields, flat-fields,
          and projections into separate files with successive file numbers starting at 1.

        - Waits for 1 exposure time because the MCS LNE output stays low for
          up to the exposure time.

        """

        # Call the base class method
        super().begin_scan()
        # We save flats, darks, and projections in separate files.
        # Set FileNumber back to 1.
        self.epics_pvs['FPFileNumber'].put(1)
        # Need to collect 3 dummy frames after changing camera to triggered mode
        self.collect_static_frames(3, False)
        # The MCS LNE output stays low after stopping MCS for up to the
        # exposure time = LNE output width.
        # Need to wait for the exposure time
        time.sleep(self.epics_pvs['ExposureTime'].value)

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Calls ``save_configuration()``.

        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.

        - Sets the speed of the rotation stage back to the maximum value.

        - Calls ``move_sample_in()``.

        - Calls the base class method.
        """

        # Save the configuration
        file_path = self.epics_pvs['FPFilePathRBV'].get(as_string=True)
        file_name = self.epics_pvs['FPFileNameRBV'].get(as_string=True)
        self.save_configuration(file_path + file_name + '.config')
        # Put the camera back in FreeRun mode and acquiring
        self.set_trigger_mode('FreeRun', 1)
        # Set the rotation speed to maximum
        max_speed = self.epics_pvs['RotationMaxSpeed'].value
        self.epics_pvs['RotationSpeed'].put(max_speed)
        # Move the sample in.  Could be out if scan was aborted while taking flat fields
        self.move_sample_in()
        # Call the base class method
        super().end_scan()

    def collect_dark_fields(self):
        """Collects dark field images.

        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumDarkFields`` PV.
        """

        super().collect_dark_fields()
        self.collect_static_frames(self.epics_pvs['NumDarkFields'].value)

    def collect_flat_fields(self):
        """Collects flat field images.

        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumFlatFields`` PV.
        """
        super().collect_flat_fields()
        self.collect_static_frames(self.epics_pvs['NumFlatFields'].value)

    def collect_projections(self):
        """Collects projections in fly scan mode.

        This does the following:
        - Sets the ``ScanStatus`` PV.

        - Moves the rotation motor to the position specified by the ``RotationStart`` PV
          minus a delta angle so that the first projection is centered on that position,
          and also compensates for the behavior of the SIS MCS.

        - Computes and sets the speed of the rotation motor so that it reaches the next projection
          angle just after the current exposure and readout are complete.

        - Sets the prescale factor of the MCS to be the number of motor pulses per rotation angle.
          The MCS is set to external trigger mode and is triggered by the stepper motor pulses
          for the rotation stage.

        - Starts the file plugin capturing in stream mode.

        - Starts the camera acquiring in external trigger mode.

        - Starts the MCS acquiring.

        - Moves the rotation motor to the position specified by the ``RotationStop`` PV.
          This triggers the acquisition of the camera.

        - Calls ``wait_camera_done()``.
        """

        super().collect_projections()
        rotation_start = self.epics_pvs['RotationStart'].value
        rotation_step = self.epics_pvs['RotationStep'].value
        num_angles = self.epics_pvs['NumAngles'].value
        rotation_stop = rotation_start + (rotation_step * num_angles)
        max_speed = self.epics_pvs['RotationMaxSpeed'].value
        self.epics_pvs['RotationSpeed'].put(max_speed)
        # Start angle is decremented a half rotation step so scan is centered on rotation_start
        # The SIS does not put out pulses until after one dwell period so need to back up an
        # additional angle step
        self.epics_pvs['Rotation'].put((rotation_start - 1.5 * rotation_step), wait=True)
        # Compute and set the motor speed
        time_per_angle = self.compute_frame_time()
        speed = rotation_step / time_per_angle
        steps_per_deg = abs(round(1./self.epics_pvs['RotationResolution'].value, 0))
        motor_speed = math.floor((speed * steps_per_deg)) / steps_per_deg
        self.epics_pvs['RotationSpeed'].put(motor_speed)
        # Set the external prescale according to the step size, use motor resolution
        # steps per degree (user unit)
        self.epics_pvs['MCSStopAll'].put(1, wait=True)
        prescale = math.floor(abs(rotation_step  * steps_per_deg))
        self.epics_pvs['MCSPrescale'].put(prescale, wait=True)
        self.set_trigger_mode('MCSExternal', num_angles)
        # Start capturing in file plugin
        self.epics_pvs['FPCapture'].put('Capture')
        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Start the MCS
        self.epics_pvs['MCSEraseStart'].put(1)
        # Wait for detector, file plugin, and MCS to be ready
        time.sleep(0.5)
        # Start the rotation motor
        self.epics_pvs['Rotation'].put(rotation_stop)
        collection_time = num_angles * time_per_angle
        self.wait_camera_done(collection_time + 60.)
