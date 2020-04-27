from epics import PV
from tomoscan import tomoscan
import time
import math

class tomoscan_13bm(tomoscan):
    """Derived class used for tomography scanning with EPICS at APS beamline 13-BM-D

    Parameters
    ----------
    pvFiles : list of str
        List of files containing EPICS pvNames to be used.
    macros : dict
        Dictionary of macro definitions to be substituted when
        reading the pvFiles
    """

    def __init__(self, pvFile, macros=[]):
        super().__init__(pvFile, macros)
        
        # Set the detector running in FreeRun mode
        self.setTriggerMode('FreeRun', 1)
        # Enable auto-increment on file writer
        self.epicsPVs['FPAutoIncrement'].put('Yes')
        # Set the SIS output pulse width to 100 us
        self.epicsPVs['MCSLNEOutputWidth'].put(0.0001)
        
    def setTriggerMode(self, triggerMode, numImages):
        """Sets the trigger mode SIS3820 and the camera. 

        Parameters
        ----------
        triggerMode : str
            Choices are: "FreeRun", "MCSInternal", or "MCSExternal"

        numImages : int
            Number of images to collect.  Ignored if triggerMode="FreeRun".
            This is used to set the ``NuseAll`` PV of the SIS MCS, the ``NumImages`` PV of the camera,
            and the ``NumCapture`` PV of the file plugin. 
        """
        if (triggerMode == 'FreeRun'):
            self.epicsPVs['CamImageMode'].put('Continuous', wait=True)
            self.epicsPVs['CamTriggerMode'].put('Off', wait=True)
            self.epicsPVs['CamExposureMode'].put('Timed', wait=True)
            self.epicsPVs['CamAcquire'].put('Acquire')
        else: # set camera to external triggering
            self.epicsPVs['CamImageMode'].put('Multiple', wait=True)
            self.epicsPVs['CamNumImages'].put(numImages, wait=True)
            self.epicsPVs['CamTriggerMode'].put('On', wait=True)
            self.epicsPVs['CamExposureMode'].put('Timed', wait=True)
            self.epicsPVs['CamTriggerOverlap'].put('ReadOut', wait=True)
            # Set number of MCS channels, NumImages, and NumCapture
            self.epicsPVs['MCSStopAll'].put(1, wait=True)
            self.epicsPVs['MCSNuseAll'].put(numImages, wait=True)
            self.epicsPVs['FPNumCapture'].put(numImages, wait=True)
  
        if (triggerMode == 'MCSExternal'):
            # Put MCS in external trigger mode
            self.epicsPVs['MCSChannelAdvance'].put('External', wait=True)
  
        if (triggerMode == 'MCSInternal'):
            self.epicsPVs['MCSChannelAdvance'].put('Internal', wait=True)
            time = self.computeFrameTime()
            self.epicsPVs['MCSDwell'].put(time, wait=True)

    def collectNFrames(self, numFrames, save=True):
        """Collects numFrames images in "MCSInternal" trigger mode for dark fields and flat fields.

        Parameters
        ----------
        numFrames : int
            Number of frames to collect.
            
        save : bool, optional
            False to disable saving frames with the file plugin.
        """
        # This is called when collecting dark fields or flat fields
        self.setTriggerMode('MCSInternal', numFrames)
        if (save):
            self.epicsPVs['FPCapture'].put('Capture')
        self.epicsPVs['CamAcquire'].put('Acquire')
        # Wait for detector and file plugin to be ready
        time.sleep(0.5)
        # Start the MCS
        self.epicsPVs['MCSEraseStart'].put(1)
        collectionTime = self.epicsPVs['MCSDwell'].value * numFrames
        self.waitCameraDone(collectionTime + 5.0)
       
    def beginScan(self):
        """Performs the operations needed at the very start of a scan.
       
        This does the following:
       
        - Calls the base class method.
       
        - Collects 3 dummy images with ``collectNFrames``.  This is required when switching from
          "FreeRun" to triggered mode on the Point Grey camera.

        - Waits for 1 exposure time because the MCS LNE output stays low for up to the exposure time.

        """

        # Call the base class method
        super().beginScan()
        # Need to collect 3 dummy frames after changing camera to triggered mode
        self.collectNFrames(3, False)
        # The MCS LNE output stays low after stopping MCS for up to the exposure time = LNE output width
        # Need to wait for the exposure time
        time.sleep(self.epicsPVs['ExposureTime'].value)

    def endScan(self):
        """Performs the operations needed at the very end of a scan.
        
        This does the following:
       
        - Calls ``saveConfiguration()``.
       
        - Put the camera back in "FreeRun" mode and acquiring so the user sees live images.
       
        - Sets the speed of the rotation stage back to the maximum value.
       
        - Calls ``moveSampleIn()``.
       
        - Calls the base class method.
        """

        # Save the configuration
        filePath = self.epicsPVs['FilePath'].get(as_string=True)
        fileName = self.epicsPVs['FileName'].get(as_string=True)
        self.saveConfiguration(filePath + fileName + '.config')
        # Put the camera back in FreeRun mode and acquiring
        self.setTriggerMode('FreeRun', 1)
        # Set the rotation speed to maximum
        maxSpeed = self.epicsPVs['RotationMaxSpeed'].value
        self.epicsPVs['RotationSpeed'].put(maxSpeed)
        # Move the sample in.  Could be out if scan was aborted while taking flat fields
        self.moveSampleIn()
        # Call the base class method
        super().endScan()

    def collectDarkFields(self):
        """Collects dark field images.
       
        Calls ``collectNFrames()`` with the number of images specified by the ``NumDarkFields`` PV. 
        """

        self.epicsPVs['ScanStatus'].put('Collecting dark fields')
        self.collectNFrames(self.epicsPVs['NumDarkFields'].value)

    def collectFlatFields(self):
        """Collects flat field images.
       
        Calls ``collectNFrames()`` with the number of images specified by the ``NumFlatFields`` PV. 
        """

        self.epicsPVs['ScanStatus'].put('Collecting flat fields')
        self.collectNFrames(self.epicsPVs['NumFlatFields'].value)
      
    def collectProjections(self):
        """Collects projections in fly scan mode.
       
        This does the following:
        - Sets the ``ScanStatus`` PV.
        
        - Moves the rotation motor to the position specified by the ``RotationStart`` PV
          minus a delta angle so that the first projection is centered on that position, 
          and also compensates for the behavior of the SIS MCS.
        
        - Computes and sets the speed of the rotation motor so that it reaches the next projection
          angle just after the current exposure and readout are complete.
        
        - Sets the prescale factor of the MCS to be the number of motor pulses per rotation angle.
          The MCS is set to external trigger mode and is triggered by the stepper motor pulses for the
          rotation stage.
        
        - Starts the file plugin capturing in stream mode.
        
        - Starts the camera acquiring in external trigger mode.
        
        - Starts the MCS acquiring.
        
        - Moves the rotation motor to the position specified by the ``RotationStop`` PV.
          This triggers the acquisition of the camera.
        
        - Calls ``waitCameraDone()``.
        """

        self.epicsPVs['ScanStatus'].put('Collecting projections')
        rotationStart = self.epicsPVs['RotationStart'].value
        rotationStep = self.epicsPVs['RotationStep'].value
        numAngles = self.epicsPVs['NumAngles'].value
        rotationStop = rotationStart + (rotationStep * numAngles)
        maxSpeed = self.epicsPVs['RotationMaxSpeed'].value
        self.epicsPVs['RotationSpeed'].put(maxSpeed)
        # Start angle is decremented a half rotation step so scan is centered on rotationStart
        # The SIS does not put out pulses until after one dwell period so need to back up an additional angle step
        self.epicsPVs['Rotation'].put((rotationStart - 1.5 * rotationStep), wait=True)
        # Compute and set the motor speed
        timePerAngle = self.computeFrameTime()
        speed = rotationStep / timePerAngle
        stepsPerDeg = abs(round(1./self.epicsPVs['RotationResolution'].value, 0))
        motorSpeed = math.floor((speed * stepsPerDeg)) / stepsPerDeg
        self.epicsPVs['RotationSpeed'].put(motorSpeed)
        # Set the external prescale according to the step size, use motor resolution steps per degree (user unit)
        self.epicsPVs['MCSStopAll'].put(1, wait=True)
        prescale = math.floor(abs(rotationStep  * stepsPerDeg))
        self.epicsPVs['MCSPrescale'].put(prescale, wait=True)
        self.setTriggerMode('MCSExternal', numAngles)
        # Start capturing in file plugin
        self.epicsPVs['FPCapture'].put('Capture')
        # Start the camera
        self.epicsPVs['CamAcquire'].put('Acquire')
        # Start the MCS
        self.epicsPVs['MCSEraseStart'].put(1)
        # Wait for detector, file plugin, and MCS to be ready
        time.sleep(0.5)
        # Start the rotation motor
        self.epicsPVs['Rotation'].put(rotationStop)
        collectionTime = numAngles * timePerAngle
        self.waitCameraDone(collectionTime + 60.)
