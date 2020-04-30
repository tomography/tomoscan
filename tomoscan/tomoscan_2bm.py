"""Software for tomography scanning with EPICS at APS beamline 2-BM-A

   Classes
   -------
   TomoScan2BM
     Derived class for tomography scanning with EPICS at APS beamline 2-BM-A
"""
import time
import math
from tomoscan import TomoScan


FrameTypeData = 0
FrameTypeDark = 1
FrameTypeFlat = 2


class TomoScan2BM(TomoScan):
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

        # Set the detector running in FreeRun mode
        self.set_trigger_mode('FreeRun', 1)
        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')
        # Set frame type label
        self.epics_pvs['CamFrameTypeZRST'].put('/exchange/data')
        self.epics_pvs['CamFrameTypeONST'].put('/exchange/data_dark')
        self.epics_pvs['CamFrameTypeTWST'].put('/exchange/data_white')


        # # Set the SIS output pulse width to 100 us
        # self.epics_pvs['MCSLNEOutputWidth'].put(0.0001)

    def set_trigger_mode(self, trigger_mode, num_images):
        """Sets the trigger mode SIS3820 and the camera.

        Parameters
        ----------
        trigger_mode : str
            Choices are: "FreeRun", "Internal", or "PSOExternal"

        num_images : int
            Number of images to collect.  Ignored if trigger_mode="FreeRun".
            This is used to set the ``NuseAll`` PV of the SIS MCS,
            the ``NumImages`` PV of the camera, and the ``NumCapture``
            PV of the file plugin.
        """
        if trigger_mode == 'FreeRun':
            self.epics_pvs['CamImageMode'].put('Continuous', wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamAcquire'].put('Acquire')
        elif (trigger_mode == 'Internal'):
            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamNumImages'].put(num_images, wait=True)
            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamAcquire'].put('Acquire')                      
        else: # set camera to external triggering
            self.epics_pvs['CamAcquire'].put(0)
            pv.wait_pv(global_PVs['CamAcquire'], 0, 2)



            self.epics_pvs['CamTriggerMode'].put('Off', wait=True)
            self.epics_pvs['CamTriggerSource'].put('Line2', wait=True)
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            self.epics_pvs['CamExposureMode'].put('Timed', wait=True)
            self.epics_pvs['CamTriggerSelector'].put('FrameStart', wait=True)
            self.epics_pvs['CamTriggerActivation'].put('RisingEdge', wait=True)

            self.epics_pvs['CamImageMode'].put('Multiple')
            self.epics_pvs['CamArrayCallbacks'].put('Enable')
            self.epics_pvs['CamFrameRateOnOff'].put(0)
            self.epics_pvs['CamAcquireTimeAuto'].put('Off')

            #self.epics_pvs['CamAcquireTime'].put(float(params.exposure_time))

            print("some issue here ... ")
            print(self.epics_pvs['CamTriggerMode'].value)
            self.epics_pvs['CamTriggerMode'].put('On', wait=True)
            print(self.epics_pvs['CamTriggerMode'].value)
            print("DONE")
            return
            self.epics_pvs['CamTriggerOverlap'].put('ReadOut', wait=True)
            self.epics_pvs['CamTriggerSource'].put('Line2', wait=True)
            # Set NumCapture
            self.epics_pvs['FPNumCapture'].put(num_images, wait=True)

    def collect_static_frames(self, num_frames, frame_type, save=True):
        """Collects num_frames images in "Internal" trigger mode for dark fields and flat fields.

        Parameters
        ----------
        num_frames : int
            Number of frames to collect.

        save : bool, optional
            False to disable saving frames with the file plugin.
        """
        # This is called when collecting dark fields or flat fields

        # Set frame type
        self.epics_pvs['CamFrameType'].put(frame_type)             
        self.set_trigger_mode('Internal', num_frames)
        if save:
            self.epics_pvs['FPCapture'].put('Capture')
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Wait for detector and file plugin to be ready
        time.sleep(0.5)
        # Start the MCS
        frame_time = self.compute_frame_time()
        collection_time = frame_time * num_frames
        self.wait_camera_done(collection_time + 5.0)

    def begin_scan(self):
        """Performs the operations needed at the very start of a scan.

        This does the following:

        - Calls the base class method.

        - Collects 3 dummy images with ``collect_static_frames``.
          This is required when switching from "FreeRun" to triggered mode
          on the Point Grey camera.

        - Waits for 1 exposure time because the MCS LNE output stays low for
          up to the exposure time.

        """

        # Call the base class method
        super().begin_scan()
        # Need to collect 3 dummy frames after changing camera to triggered mode
        self.collect_static_frames(3, FrameTypeData, False)
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
        file_path = self.epics_pvs['FilePath'].get(as_string=True)
        file_name = self.epics_pvs['FileName'].get(as_string=True)
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

        self.epics_pvs['ScanStatus'].put('Collecting dark fields')
        self.collect_static_frames(self.epics_pvs['NumDarkFields'].value, FrameTypeDark)

    def collect_flat_fields(self):
        """Collects flat field images.

        Calls ``collect_static_frames()`` with the number of images specified
        by the ``NumFlatFields`` PV.
        """

        self.epics_pvs['ScanStatus'].put('Collecting flat fields')
        self.collect_static_frames(self.epics_pvs['NumFlatFields'].value, FrameTypeFlat)

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

        self.epics_pvs['ScanStatus'].put('Collecting projections')

        # Set frame type
        self.epics_pvs['CamFrameType'].put(FrameTypeData)
        
        rotation_start = self.epics_pvs['RotationStart'].value
        rotation_step = self.epics_pvs['RotationStep'].value
        num_angles = self.epics_pvs['NumAngles'].value
        rotation_stop = rotation_start + (rotation_step * num_angles)
        max_speed = self.epics_pvs['RotationMaxSpeed'].value
        # Compute and set the motor speed
        time_per_angle = self.compute_frame_time()
        motor_speed = rotation_step / time_per_angle

        self.epics_pvs['PSOstartPos'].put(rotation_start)
        self.epics_pvs['PSOendPos'].put(rotation_stop)
        self.epics_pvs['PSOslewSpeed'].put(motor_speed)
        self.epics_pvs['PSOscanDelta'].put(rotation_step)

        calc_num_proj = self.epics_pvs['PSOcalcProjections'].value
        
        if calc_num_proj != num_angles:
            # log.warning('  *** *** Changing number of projections from: %s to: %s' % (params.num_angles, int(calc_num_proj)))
            num_angles = calc_num_proj
        self.epics_pvs['PSOscanControl'].put('Standard')

        # Taxi before starting capture
        self.epics_pvs['PSOtaxi'].put(1)
        wait_pv(epics_pvs['FlyTaxi'], 0)

        self.set_trigger_mode('PSOExternal', num_angles)

        # Start capturing in file plugin
        self.epics_pvs['FPCapture'].put('Capture')
        # Start the camera
        self.epics_pvs['CamAcquire'].put('Acquire')
        # Start fly scan
        self.epics_pvs['PSOrun'].put(1)
        # wait for acquire to finish 
        # time_per_angle = self.compute_frame_time()
        # collection_time = num_angles * time_per_angle
        # self.wait_camera_done(collection_time + 60.)
        wait_pv(global_PVs['FlyRun'], 0)

    def wait_pv(self, pv, wait_val, timeout=-1):
        """Wait on a pv to be a value until max_timeout (default forever)
           delay for pv to change   
        """

        time.sleep(.01)
        startTime = time.time()
        while(True):
            pv_val = pv.get()
            if type(pv_val) == float:
                if abs(pv_val - wait_val) < EPSILON:
                    return True
            if (pv_val != wait_val):
                if timeout > -1:
                    curTime = time.time()
                    diffTime = curTime - startTime
                    if diffTime >= timeout:
                        logging.error('  *** ERROR: DROPPED IMAGES ***')
                        logging.error('  *** wait_pv(%s, %d, %5.2f reached max timeout. Return False' % (pv.pvname, wait_val, timeout))


                        return False
                time.sleep(.01)
            else:
                return True

