from epics import PV
import json
import time
import threading
import signal
import logging
from datetime import timedelta

class scanAbortError(Exception):
    '''Exception raised when user wants to abort a scan.
    '''
    pass

class cameraTimeoutError(Exception):
    '''Exception raised when the camera times out during a scan.
    '''
    pass

class tomoscan:
    """ Base class used for tomography scanning with EPICS

    Constructor parameters
    ----------------------
    pvFiles : list of str
        List of files containing EPICS pvNames to be used.
    macros : dict
        Dictionary of macro definitions to be substituted when
        reading the pvFiles
    """

    def __init__(self, pvFiles, macros=[]):
        """
        Parameters
        ----------
        pvFiles : list of str
            List of files containing EPICS pvNames to be used.
        macros : dict
            Dictionary of macro definitions to be substituted when
            reading the pvFiles
        """

        logging.basicConfig(level=logging.INFO)
        self.configPVs = {}
        self.controlPVs = {}
        self.pvPrefixes = {}
        if (isinstance(pvFiles, list) == False):
            pvFiles = [pvFiles]
        for pvFile in pvFiles:
            self.readPVFile(pvFile, macros)

        if (('Rotation' in self.controlPVs) == False):
            logging.error('RotationPVName must be present in autoSettingsFile')
            quit()
        if (('Camera' in self.pvPrefixes) == False):
            logging.error('CameraPVPrefix must be present in autoSettingsFile')
            quit()
        if (('FilePlugin' in self.pvPrefixes) == False):
            logging.error('FilePluginPVPrefix must be present in autoSettingsFile')
            quit()
                
        rotationPVName = self.controlPVs['Rotation'].pvname
        self.controlPVs['RotationSpeed']      = PV(rotationPVName + '.VELO')
        self.controlPVs['RotationMaxSpeed']   = PV(rotationPVName + '.VMAX')
        self.controlPVs['RotationResolution'] = PV(rotationPVName + '.MRES')

        prefix = self.pvPrefixes['Camera']
        camPrefix = prefix + 'cam1:'
        self.controlPVs['CamManufacturer']      = PV(camPrefix + 'Manufacturer_RBV')
        self.controlPVs['CamModel']             = PV(camPrefix + 'Model_RBV')
        self.controlPVs['CamAcquire']           = PV(camPrefix + 'Acquire')
        self.controlPVs['CamAcquireBusy']       = PV(camPrefix + 'AcquireBusy')
        self.controlPVs['CamImageMode']         = PV(camPrefix + 'ImageMode')
        self.controlPVs['CamTriggerMode']       = PV(camPrefix + 'TriggerMode')
        self.controlPVs['CamNumImages']         = PV(camPrefix + 'NumImages')
        self.controlPVs['CamNumImagesCounter']  = PV(camPrefix + 'NumImagesCounter_RBV')
        self.controlPVs['CamAcquireTime']       = PV(camPrefix + 'AcquireTime')
        self.controlPVs['CamAcquireTimeRBV']    = PV(camPrefix + 'AcquireTime_RBV')
        self.controlPVs['CamBinX']              = PV(camPrefix + 'BinX')
        self.controlPVs['CamBinY']              = PV(camPrefix + 'BinY')
        self.controlPVs['CamWaitForPlugins']    = PV(camPrefix + 'WaitForPlugins')
        
        # If this is a Point Grey camera then assume we are running ADSpinnaker
        # and create some PVs specific to that driver
        manufacturer = self.controlPVs['CamManufacturer'].get(as_string=True)
        model = self.controlPVs['CamModel'].get(as_string=True)
        if (manufacturer.find('Point Grey') != -1):
            self.controlPVs['CamExposureMode']   = PV(camPrefix + 'ExposureMode')
            self.controlPVs['CamTriggerOverlap'] = PV(camPrefix + 'TriggerOverlap')
            self.controlPVs['CamPixelFormat']    = PV(camPrefix + 'PixelFormat')
            if (model.find('Grasshopper3') != -1):
                self.controlPVs['CamVideoMode']  = PV(camPrefix + 'GC_VideoMode_RBV')

        # Set some initial PV values                
        self.controlPVs['CamWaitForPlugins'].put('Yes')
        self.controlPVs['StartScan'].put(0)
  
        prefix = self.pvPrefixes['FilePlugin']
        self.controlPVs['FPFileWriteMode']   = PV(prefix + 'FileWriteMode')
        self.controlPVs['FPNumCapture']      = PV(prefix + 'NumCapture')
        self.controlPVs['FPNumCaptured']     = PV(prefix + 'NumCaptured_RBV')
        self.controlPVs['FPCapture']         = PV(prefix + 'Capture')
        self.controlPVs['FPFilePath']        = PV(prefix + 'FilePath')
        self.controlPVs['FPFileName']        = PV(prefix + 'FileName')
        self.controlPVs['FPFileNumber']      = PV(prefix + 'FileNumber')
        self.controlPVs['FPAutoIncrement']   = PV(prefix + 'AutoIncrement')
        self.controlPVs['FPFullFileName']    = PV(prefix + 'FullFileName_RBV')
        self.controlPVs['FPAutoSave']        = PV(prefix + 'AutoSave')
        self.controlPVs['FPEnableCallbacks'] = PV(prefix + 'EnableCallbacks')
        
        # Set some initial PV values
        filePath = self.configPVs['FilePath'].get(as_string=True)
        self.controlPVs['FPFilePath'].put(filePath)
        fileName = self.configPVs['FileName'].get(as_string=True)
        self.controlPVs['FPFileName'].put(fileName)
        self.controlPVs['FPAutoSave'].put('No')
        self.controlPVs['FPFileWriteMode'].put('Stream')
        self.controlPVs['FPEnableCallbacks'].put('Enable')

        if ('MCS' in self.pvPrefixes):             
            prefix = self.pvPrefixes['MCS']
            self.controlPVs['MCSEraseStart']      = PV(prefix + 'EraseStart')
            self.controlPVs['MCSStopAll']         = PV(prefix + 'StopAll')
            self.controlPVs['MCSPrescale']        = PV(prefix + 'Prescale')
            self.controlPVs['MCSDwell']           = PV(prefix + 'Dwell')
            self.controlPVs['MCSLNEOutputWidth']  = PV(prefix + 'LNEOutputWidth')
            self.controlPVs['MCSChannelAdvance']  = PV(prefix + 'ChannelAdvance')
            self.controlPVs['MCSMaxChannels']     = PV(prefix + 'MaxChannels')
            self.controlPVs['MCSNuseAll']         = PV(prefix + 'NuseAll')
 
        self.epicsPVs = {**self.configPVs, **self.controlPVs}
        # Wait 1 second for all PVs to connect
        time.sleep(1)
        self.checkPVsConnected()
        
        # Configure callbacks on a few PVs
        self.epicsPVs['MoveSampleIn'].add_callback(self.pvCallback)
        self.epicsPVs['MoveSampleOut'].add_callback(self.pvCallback)
        self.epicsPVs['StartScan'].add_callback(self.pvCallback)
        self.epicsPVs['AbortScan'].add_callback(self.pvCallback)
        self.epicsPVs['ExposureTime'].add_callback(self.pvCallback)
                
         # Set ^C interrupt to abort the scan
        signal.signal(signal.SIGINT, self.signalHandler)

    def signalHandler(self, sig, frame):
        """Calls abortScan when ^C is typed"""
        if (sig == signal.SIGINT):
            self.abortScan();

    def pvCallback(self, pvname=None, value=None, char_value=None, **kw):
        """Callback function that is called by pyEpics when certain EPICS PVs are changed

        The PVs that are handled are:

        - ``StartScan`` : Calls ``runFlyScan()``

        - ``AbortScan`` : Calls ``abortScan()``
        
        - ``MoveSampleIn`` : Runs ``MoveSampleIn()`` in a new thread.

        - ``MoveSampleOut`` : Runs ``MoveSampleOut()`` in a new thread.

        - ``ExposureTime`` : Runs ``setExposureTime()`` in a new thread.

        """

        logging.info('pvCallback pvName=%s, value=%s, char_value=%s' % (pvname, value, char_value))
        if ((pvname.find('MoveSampleIn') != -1) and (value == 1)):
            thread = threading.Thread(target=self.moveSampleIn, args=())
            thread.start()
        if ((pvname.find('MoveSampleOut') != -1) and (value == 1)):
            thread = threading.Thread(target=self.moveSampleOut, args=())
            thread.start()        
        if ((pvname.find('ExposureTime') != -1)):
            thread = threading.Thread(target=self.setExposureTime, args=(value,))
            thread.start()        
        if ((pvname.find('StartScan') != -1) and (value == 1)):
            self.runFlyScan()
        if ((pvname.find('AbortScan') != -1) and (value == 1)):
            self.abortScan()

    def showPVs(self):
        """Prints the current values of all EPICS PVs in use.
        
        The values are printed in three sections:
          
        - configPVs : The PVs that are part of the scan configuration and are saved by saveConfiguration()
        
        - controlPVs : The PVs that are used for EPICS control and status, but are not saved by saveConfiguration()
        
        - pvPrefixes : The prefixes for PVs that are used for the areaDetector camera, file plugin, etc.
        """

        print('configPVS:')
        for pv in self.configPVs:
            print(pv, ':', self.configPVs[pv].get(as_string=True))

        print('')
        print('controlPVS:')
        for pv in self.controlPVs:
            print(pv, ':', self.controlPVs[pv].get(as_string=True))

        print('')
        print('pvPrefixes:')
        for pv in self.pvPrefixes:
            print(pv, ':', self.pvPrefixes[pv])
            
    def checkPVsConnected(self):
        """Checks whether all EPICS PVs are connected.
        
        Returns
        -------
        bool 
            True if all PVs are connected, otherwise False.
        """

        allConnected = True
        for pv in self.epicsPVs:
            if (self.epicsPVs[pv].connected == False):
                logging.error('PV %s is not connected' % self.epicsPVs[pv].pvname)
                allConnected = False
        return allConnected

    def readPVFile(self, pvFile, macros):
        """Reads a file containing a list of EPICS PVs to be used by tomoscan.
        
        
        Parameters
        ----------
        pvFile : str
          Name of the file to read
        macros: dict
          Dictionary of macro substitution to perform when reading the file
        """
        
        f = open(pvFile)
        lines = f.read()
        f.close()
        lines = lines.splitlines()
        for line in lines:
            isConfigPV = True
            if (line.find('#controlPV') != -1):
                line = line.replace('#controlPV', '')
                isConfigPV = False
            line = line.lstrip()
            # Skip lines starting with #
            if (line.startswith('#')):
                continue
            # Skip blank lines
            if (line == ''):
                continue
            pvname = line
            # Do macro substitution on the pvName
            for key in macros:
                 pvname = pvname.replace(key, macros[key])
            # Replace macros in dictionary key with nothing
            dictentry = line
            for key in macros:
                 dictentry = dictentry.replace(key, '')
            pv = PV(pvname)
            if (isConfigPV == True):
                self.configPVs[dictentry] = pv
            else:
                self.controlPVs[dictentry] = pv
            if (dictentry.find('PVName') != -1):
                pvname = pv.value
                de = dictentry.replace('PVName', '')
                self.controlPVs[de] = PV(pvname)
            if (dictentry.find('PVPrefix') != -1):
                pvprefix = pv.value
                de = dictentry.replace('PVPrefix', '')
                self.pvPrefixes[de] = pvprefix

    def moveSampleIn(self):
        """Moves the sample to the in beam position for collecting projections.
        
        The in-beam position is defined by the ``SampleInX`` and ``SampleInY`` PVs.
        
        Which axis to move is defined by the ``FlatFieldAxis`` PV, 
        which can be ``X``, ``Y``, or ``Both``.
        """

        axis = self.epicsPVs['FlatFieldAxis'].get(as_string=True)
        logging.info('moveSampleIn axis: %s', axis)
        if (axis == 'X') or (axis == 'Both'):
            position = self.epicsPVs['SampleInX'].value
            self.epicsPVs['SampleX'].put(position, wait=True)
            
        if (axis == 'Y') or (axis == 'Both'):
            position = self.epicsPVs['SampleInY'].value
            self.epicsPVs['SampleY'].put(position, wait=True)

    def moveSampleOut(self):
        """Moves the sample to the out of beam position for collecting flat fields.
        
        The out of beam position is defined by the ``SampleOutX`` and ``SampleOutY`` PVs.
        
        Which axis to move is defined by the ``FlatFieldAxis`` PV,
        which can be ``X``, ``Y``, or ``Both``.
        """

        axis = self.epicsPVs['FlatFieldAxis'].get(as_string=True)
        logging.info('moveSampleOut axis: %s', axis)
        if (axis == 'X') or (axis == 'Both'):
            position = self.epicsPVs['SampleOutX'].value
            self.epicsPVs['SampleX'].put(position, wait=True)
            
        if (axis == 'Y') or (axis == 'Both'):
            position = self.epicsPVs['SampleOutY'].value
            self.epicsPVs['SampleY'].put(position, wait=True)

    def saveConfiguration(self, fileName):
        """Saves the current configuration PVs to a file.        
        
        A new dictionary is created, containing the key for each PV in the ``configPVs`` dictionary
        and the current value of that PV.  This dictionary is written to the file in JSON format.

        Parameters
        ----------
        fileName str
            The name of the file to save to.
        """

        d = {}
        for pv in self.configPVs:
            d[pv] = self.configPVs[pv].get(as_string=True)
        f = open(fileName, 'w')
        json.dump(d, f, indent=2)
        f.close()
    
    def loadConfiguration(self, fileName):
        """Loads a configuration from a file into the EPICS PVs.        
        
        Parameters
        ----------
        fileName str
            The name of the file to save to.
        """

        f = open(fileName, 'r')
        d = json.load(f)
        f.close()
        for pv in d:
            self.configPVs[pv].put(d[pv])

    def openShutter(self):
        """Opens the shutter to collect flat fields or projections.        
        
        The value in the ``OpenShutterValue`` PV is written to the ``OpenShutter`` PV.
        """

        if (self.epicsPVs['OpenShutter'] != None):
            value = self.epicsPVs['OpenShutterValue'].get(as_string=True)
            self.epicsPVs['OpenShutter'].put(value, wait=True)

    def closeShutter(self):
        """Closes the shutter to collect dark fields.        
        
        The value in the ``CloseShutterValue`` PV is written to the ``CloseShutter`` PV.
        """
        if (self.epicsPVs['CloseShutter'] != None):
            value = self.epicsPVs['CloseShutterValue'].get(as_string=True)
            self.epicsPVs['CloseShutter'].put(value, wait=True)

    def setExposureTime(self, exposureTime=None):
        """Sets the camera exposure time.        
        
        The exposureTime is written to the camera's ``AcquireTime`` PV.

        Parameters
        ----------
        exposureTime float, optional
            The exposure time to use. If None then the value of the ``ExposureTime`` PV is used.
        """

        if (exposureTime == None):
            exposureTime = self.epicsPVs['ExposureTime'].value
        self.epicsPVs['CamAcquireTime'].put(exposureTime)

    def beginScan(self):
        """Performs the operations needed at the very start of a scan.
        
        This base class method does the following:        

        - Sets the status string in the ``ScanStatus`` PV.
        
        - Stops the camera acquisition.
        
        - Calls ``setExposureTime()``
        
        - Copies the ``FilePath`` and ``FileName`` PVs to the areaDetector file plugin.
        
        It is expected that most derived classes will override this method.  In most cases they
        should first call this base class method, and then perform any beamline-specific operations.
        """

        self.scanIsRunning = True
        self.epicsPVs['ScanStatus'].put('Beginning scan')
        # Stop the camera since it could be in free-run mode
        self.epicsPVs['CamAcquire'].put(0, wait=True)
        # Set the exposure time
        self.setExposureTime()
        # Set the file path, file name and file number
        self.epicsPVs['FPFilePath'].put(self.epicsPVs['FilePath'].value)
        self.epicsPVs['FPFileName'].put(self.epicsPVs['FileName'].value)

    def endScan(self):
        """Performs the operations needed at the very end of a scan.
        
        This base class method does the following:        

        - Sets the status string in the ``ScanStatus`` PV.

        - If the ``ReturnRotation`` PV is Yes then it moves the rotation motor back to the 
          position defined by the ``RotationStart`` PV.  It does not wait for the move to complete.
        
        - Sets the ``StartScan`` PV to 0.  This PV is an EPICS ``busy`` record.  Normally EPICS clients
          that start a scan with the ``StartScan`` PV will wait for ``StartScan`` to return to 0, often
          using the ``ca_put_callback()`` mechanism.

        It is expected that most derived classes will override this method.  In most cases they
        should first perform any beamline-specific operations and then call this base class method.
        This ensures that the scan is really complete before ``StartScan`` is set to 0. 
        """

        returnRotation = self.epicsPVs['ReturnRotation'].get(as_string=True)
        if (returnRotation == 'Yes'):
            self.epicsPVs['Rotation'].put(self.epicsPVs['RotationStart'].value)
        self.epicsPVs['ScanStatus'].put('Scan complete')
        self.epicsPVs['StartScan'].put(0)
        self.scanIsRunning = False

    def flyScan(self):
        try:
            rotationStart = self.epicsPVs['RotationStart'].value
            rotationStep = self.epicsPVs['RotationStart'].value
            numAngles = self.epicsPVs['NumAngles'].value
            rotationStop = rotationStart + (numAngles * rotationStep)
            numDarkFields = self.epicsPVs['NumDarkFields'].value
            darkFieldMode = self.epicsPVs['DarkFieldMode'].get(as_string=True)
            numFlatFields = self.epicsPVs['NumFlatFields'].value
            flatFieldMode = self.epicsPVs['FlatFieldMode'].get(as_string=True)
            # Move the rotation to the start
            self.epicsPVs['Rotation'].put(rotationStart, wait=True)
            # Prepare for scan
            self.beginScan()
            # Collect the pre-scan dark fields if required
            if (numDarkFields > 0) and ((darkFieldMode == 'Start') or (darkFieldMode == 'Both')):
                self.closeShutter()
                self.collectDarkFields()
            # Open the shutter 
            self.openShutter()
            # Collect the pre-scan flat fields if required
            if (numFlatFields > 0) and ((flatFieldMode == 'Start') or (flatFieldMode == 'Both')):
                self.moveSampleOut()
                self.collectFlatFields()
            # Collect the projections
            self.moveSampleIn()
            self.collectProjections()
            # Collect the post-scan flat fields if required
            if (numFlatFields > 0) and ((flatFieldMode == 'End') or (flatFieldMode == 'Both')):
                self.moveSampleOut()
                self.collectFlatFields()
                self.moveSampleIn()
            # Collect the post-scan dark fields if required
            if (numDarkFields > 0) and ((darkFieldMode == 'End') or (darkFieldMode == 'Both')):
                self.closeShutter()
                self.collectDarkFields()
                self.openShutter()

        except scanAbortError:
            logging.error('Scan aborted')
        except cameraTimeoutError:
            logging.error('Camera timeout')

        # Finish scan
        self.endScan()

    def runFlyScan(self):
        thread = threading.Thread(target=self.flyScan, args=())
        thread.start()
        
    def abortScan(self):
        self.scanIsRunning = False   

    def computeFrameTime(self):
        self.setExposureTime()
        # The readout time of the camera depends on the model, and things like the PixelFormat, VideoMode, etc.
        # The measured times in ms with 100 microsecond exposure time and 1000 frames without dropping
        cameraModel = self.epicsPVs['CamModel'].get(as_string=True)
        pixelFormat = self.epicsPVs['CamPixelFormat'].get(as_string=True)
        if (cameraModel == 'Grasshopper3 GS3-U3-23S6M'): 
            videoMode   = self.epicsPVs['CamVideoMode'].get(as_string=True)
            readoutTimes = {'Mono8':        {'Mode0': 6.2, 'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 7.9},
                            'Mono12Packed': {'Mode0': 9.2, 'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 11.5},
                            'Mono16':       {'Mode0': 12.2,'Mode1': 6.2, 'Mode5': 6.2, 'Mode7': 12.2}}       
            readout = readoutTimes[pixelFormat][videoMode]/1000.
        
        if (readout == None):
            logging.error('Unsupported combination of camera model, pixel format and video mode: %s %s %s' 
                          % (cameraModel, pixelFormat, videoMode))
            return 0

        # We need to use the actual exposure time that the camera is using, not the requested exposure time
        exposure = self.epicsPVs['CamAcquireTimeRBV'].value
        # Add 1 or 5 ms to exposure time for margin
        if (exposure > 2.3):
            time = exposure + .005 
        else:
            time = exposure + .001

        # If the time is less than the readout time then use the readout time
        if (time < readout):
            time = readout
        return time

    def waitCameraDone(self, timeout):
        startTime = time.time()
        while(True):
            if (self.epicsPVs['CamAcquireBusy'].value == 0):
                return
            if (self.scanIsRunning == False):
                raise scanAbortError
            time.sleep(0.2)
            numCollected  = self.epicsPVs['CamNumImagesCounter'].value
            numImages     = self.epicsPVs['CamNumImages'].value
            numSaved      = self.epicsPVs['FPNumCaptured'].value
            numToSave     = self.epicsPVs['FPNumCapture'].value
            currentTime = time.time()
            elapsedTime = currentTime - startTime
            remainingTime = elapsedTime * (numImages - numCollected) / max(float(numCollected),1)
            collectProgress = str(numCollected) + '/' + str(numImages)
            logging.info('Collected %s', collectProgress)
            self.epicsPVs['ImagesCollected'].put(collectProgress)
            saveProgress = str(numSaved) + '/' + str(numToSave)
            logging.info('Saved %s', saveProgress)
            self.epicsPVs['ImagesSaved'].put(saveProgress)
            self.epicsPVs['ElapsedTime'].put(str(timedelta(seconds=int(elapsedTime))))
            self.epicsPVs['RemainingTime'].put(str(timedelta(seconds=int(remainingTime))))
            if (timeout > 0):
                if elapsedTime >= timeout:
                    raise cameraTimeoutError()
