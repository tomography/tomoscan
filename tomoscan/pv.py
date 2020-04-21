# #########################################################################
# Copyright (c) 2019-2020, UChicago Argonne, LLC. All rights reserved.    #
#                                                                         #
# Copyright 2019-2020. UChicago Argonne, LLC. This software was produced  #
# under U.S. Government contract DE-AC02-06CH11357 for Argonne National   #
# Laboratory (ANL), which is operated by UChicago Argonne, LLC for the    #
# U.S. Department of Energy. The U.S. Government has rights to use,       #
# reproduce, and distribute this software.  NEITHER THE GOVERNMENT NOR    #
# UChicago Argonne, LLC MAKES ANY WARRANTY, EXPRESS OR IMPLIED, OR        #
# ASSUMES ANY LIABILITY FOR THE USE OF THIS SOFTWARE.  If software is     #
# modified to produce derivative works, such modified software should     #
# be clearly marked, so as not to confuse it with the version available   #
# from ANL.                                                               #
#                                                                         #
# Additionally, redistribution and use in source and binary forms, with   #
# or without modification, are permitted provided that the following      #
# conditions are met:                                                     #
#                                                                         #
#     * Redistributions of source code must retain the above copyright    #
#       notice, this list of conditions and the following disclaimer.     #
#                                                                         #
#     * Redistributions in binary form must reproduce the above copyright #
#       notice, this list of conditions and the following disclaimer in   #
#       the documentation and/or other materials provided with the        #
#       distribution.                                                     #
#                                                                         #
#     * Neither the name of UChicago Argonne, LLC, Argonne National       #
#       Laboratory, ANL, the U.S. Government, nor the names of its        #
#       contributors may be used to endorse or promote products derived   #
#       from this software without specific prior written permission.     #
#                                                                         #
# THIS SOFTWARE IS PROVIDED BY UChicago Argonne, LLC AND CONTRIBUTORS     #
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT       #
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS       #
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL UChicago     #
# Argonne, LLC OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,        #
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,    #
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;        #
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER        #
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT      #
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN       #
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE         #
# POSSIBILITY OF SUCH DAMAGE.                                             #
# #########################################################################

"""
Epics PV definition for Sector 2-BM.
"""

import time

from epics import PV
from tomoscan import log

TESTING = True

ShutterAisFast = True           # True: use m7 as shutter; False: use Front End Shutter

ShutterAOpen_Value = 1
ShutterAClose_Value = 0
ShutterBOpen_Value = 1
ShutterB_Close_Value = 0

Recursive_Filter_Type = 'RecursiveAve'

EPSILON = 0.1


def wait_pv(pv, wait_val, max_timeout_sec=-1):

    # wait on a pv to be a value until max_timeout (default forever)   
    # delay for pv to change
    time.sleep(.01)
    startTime = time.time()
    while(True):
        pv_val = pv.get()
        if type(pv_val) == float:
            if abs(pv_val - wait_val) < EPSILON:
                return True
        if (pv_val != wait_val):
            if max_timeout_sec > -1:
                curTime = time.time()
                diffTime = curTime - startTime
                if diffTime >= max_timeout_sec:
                    log.error('  *** ERROR: DROPPED IMAGES ***')
                    log.error('  *** wait_pv(%s, %d, %5.2f reached max timeout. Return False' % (pv.pvname, wait_val, max_timeout_sec))


                    return False
            time.sleep(.01)
        else:
            return True


def init_general_PVs(params):

    global_PVs = {}

    global_PVs['Station'] = PV('2bmS1:ExpInfo:Station.VAL')
    global_PVs['Camera_IOC_Prefix'] = PV('2bmS1:ExpInfo:CameraIOCPrefix.VAL')

    # shutter pv's
    global_PVs['ShutterAOpen'] = PV('2bma:A_shutter:open.VAL')
    global_PVs['ShutterAClose'] = PV('2bma:A_shutter:close.VAL')
    global_PVs['ShutterAMoveStatus'] = PV('PA:02BM:STA_A_FES_OPEN_PL')
    global_PVs['ShutterBOpen'] = PV('2bma:B_shutter:open.VAL')
    global_PVs['ShutterB_Close'] = PV('2bma:B_shutter:close.VAL')
    global_PVs['ShutterB_Move_Status'] = PV('PA:02BM:STA_B_SBS_OPEN_PL')


    # Experimment Info
    global_PVs['UserName'] = PV('2bmS1:ExpInfo:UserName.VAL')
    global_PVs['UserEmail'] = PV('2bmS1:ExpInfo:UserEmail.VAL')
    global_PVs['UserBadge'] = PV('2bmS1:ExpInfo:UserBadge.VAL')
    global_PVs['ProposalNumber'] = PV('2bmS1:ExpInfo:ProposalNumber.VAL')
    global_PVs['ProposalTitle'] = PV('2bmS1:ExpInfo:ProposalTitle.VAL')
    global_PVs['UserInstitution'] = PV('2bmS1:ExpInfo:UserInstitution.VAL')
    global_PVs['UserInfoUpdate'] = PV('2bmS1:ExpInfo:UserInfoUpdate.VAL')
    global_PVs['Time'] = PV('S:IOC:timeOfDayISO8601')


    global_PVs['ScintillatorType'] = PV('2bmS1:ExpInfo:ScintillatorType.VAL')
    global_PVs['ScintillatorThickness'] = PV('2bmS1:ExpInfo:ScintillatorThickness.VAL')

    global_PVs['ImagePixelSize'] = PV('2bmS1:ExpInfo:ImagePixelSize.VAL')
    global_PVs['DetectorPixelSize'] = PV('2bmS1:ExpInfo:DetectorPixelSize.VAL')
    global_PVs['CameraObjective'] = PV('2bmS1:CameraObjective.VAL')
    global_PVs['CameraTubeLength'] = PV('22bmS1:ExpInfo:CameraTubeLength.VAL')

    # energy info
    global_PVs['Energy'] = PV('2bmS1:ExpInfo:Energy.VAL')
    global_PVs['EnergyMode'] = PV('2bmS1:ExpInfo:EnergyMode.VAL')
    global_PVs['Filters'] = PV('2bmS1:ExpInfo:Filters.VAL')

    # scan info
    global_PVs['RotationStart'] = PV('2bmS1:ExpInfo:RotationStart.VAL')
    global_PVs['RotationEnd'] = PV('2bmS1:ExpInfo:RotationEnd.VAL')
    global_PVs['RotationStep'] = PV('2bmS1:ExpInfo:RotationStep.VAL')
    global_PVs['NumAngles'] = PV('2bmS1:ExpInfo:NumAngles.VAL')
    global_PVs['ReturnRotation'] = PV('2bmS1:ExpInfo:ReturnRotation')

    global_PVs['NumFlatFields'] = PV('2bmS1:ExpInfo:NumFlatFields.VAL')
    global_PVs['FlatFieldMode'] = PV('2bmS1:ExpInfo:FlatFieldMode')
    global_PVs['FlatFieldValue'] = PV('2bmS1:ExpInfo:FlatFieldValue')

    global_PVs['NumDarkFields'] = PV('2bmS1:ExpInfo:NumDarkFields.VAL')
    global_PVs['DarkFieldMode'] = PV('2bmS1:ExpInfo:DarkFieldMode')
    global_PVs['DarkFieldValue'] = PV('2bmS1:ExpInfo:DarkFieldValue')

    global_PVs['FlatFieldAxis'] = PV('2bmS1:ExpInfo:FlatFieldAxis')
    global_PVs['SampleInX'] = PV('2bmS1:ExpInfo:SampleInX')
    global_PVs['SampleOutX'] = PV('2bmS1:ExpInfo:SampleOutX')
    global_PVs['SampleInY'] = PV('2bmS1:ExpInfo:SampleInY')
    global_PVs['SampleOutY'] = PV('2bmS1:ExpInfo:SampleOutY')

    global_PVs['ScanType'] = PV('2bmS1:ExpInfo:ScanType.VAL')
    global_PVs['SleepTime'] = PV('2bmS1:ExpInfo:SleepTime.VAL')
    global_PVs['VerticalScanStart'] = PV('2bmS1:ExpInfo:VerticalScanStart.VAL')
    global_PVs['VerticalScanEnd'] = PV('2bmS1:ExpInfo:VerticalScanEnd.VAL')
    global_PVs['VerticalScanStepSize'] = PV('2bmS1:ExpInfo:VerticalScanStepSize.VAL')
    global_PVs['HorizontalScanStart'] = PV('2bmS1:ExpInfo:HorizontalScanStart.VAL')
    global_PVs['HorizontalScanEnd'] = PV('2bmS1:ExpInfo:HorizontalScanEnd.VAL')
    global_PVs['HorizontalScanStepSize'] = PV('2bmS1:ExpInfo:HorizontalScanStepSize.VAL')

    # sample info
    global_PVs['SampleName'] = PV('2bmS1:ExpInfo:SampleName')
    global_PVs['SampleDescription1'] = PV('2bmS1:ExpInfo:SampleDescription1.VAL')
    global_PVs['SampleDescription2'] = PV('2bmS1:ExpInfo:SampleDescription2.VAL')
    global_PVs['SampleDescription3'] = PV('2bmS1:ExpInfo:SampleDescription3.VAL')

    # environment info
    global_PVs['UseFurnace'] = PV('2bmS1:ExpInfo:UseFurnace.VAL')
    global_PVs['FurnaceInPosition'] = PV('2bmS1:ExpInfo:FurnaceInPosition.VAL')
    global_PVs['FurnaceOutPosition'] = PV('2bmS1:ExpInfo:FurnaceOutPosition.VAL')

    # data management info
    global_PVs['ExperimentYearMonth'] = PV('2bmS1:ExpInfo:ExperimentYearMonth.VAL')
    global_PVs['UserLastName'] = PV('2bmS1:ExpInfo:UserLastName.VAL')
    global_PVs['RemoteDataTransfer'] = PV('2bmS1:ExpInfo:RemoteDataTrasfer.VAL')
    global_PVs['RemoteAnalysisDir'] = PV('2bmS1:ExpInfo:RemoteAnalysisDir.VAL')

    if params.station == '2-BM-A':
        log.info('*** Running in station A:')
        # Set sample stack motor pv's:
        global_PVs['SampleX'] = PV('2bma:m49.VAL')
        global_PVs['SampleXSET'] = PV('2bma:m49.SET')
        global_PVs['SampleY'] = PV('2bma:m20.VAL')
        global_PVs['SampleOmega'] = PV('2bma:m82.VAL') # Aerotech ABR-250
        global_PVs['SampleOmegaRBV'] = PV('2bma:m82.RBV') # Aerotech ABR-250
        global_PVs['SampleOmegaCnen'] = PV('2bma:m82.CNEN') 
        global_PVs['SampleOmegaAccl'] = PV('2bma:m82.ACCL') 
        global_PVs['SampleOmegaStop'] = PV('2bma:m82.STOP') 
        global_PVs['SampleOmegaSet'] = PV('2bma:m82.SET') 
        global_PVs['SampleOmegaVelo'] = PV('2bma:m82.VELO') 
        global_PVs['SampleXCent'] = PV('2bmS1:m2.VAL')
        global_PVs['SampleZCent'] = PV('2bmS1:m1.VAL') 
        global_PVs['SamplePitch'] = PV('2bma:m50.VAL')
        global_PVs['SampleRoll'] = PV('2bma:m51.VAL')
        global_PVs['CameraDistance'] = PV('2bma:m22.VAL')
       
        # Set FlyScan
        global_PVs['FlyScanDelta'] = PV('2bma:PSOFly2:scanDelta')
        global_PVs['FlyStartPos'] = PV('2bma:PSOFly2:startPos')
        global_PVs['FlyEndPos'] = PV('2bma:PSOFly2:endPos')
        global_PVs['FlySlewSpeed'] = PV('2bma:PSOFly2:slewSpeed')
        global_PVs['FlyTaxi'] = PV('2bma:PSOFly2:taxi')
        global_PVs['FlyRun'] = PV('2bma:PSOFly2:fly')
        global_PVs['FlyScanControl'] = PV('2bma:PSOFly2:scanControl')
        global_PVs['FlyCalcProjections'] = PV('2bma:PSOFly2:numTriggers')
        global_PVs['OmegaArray'] = PV('2bma:PSOFly2:motorPos.AVAL')

        global_PVs['FastShutter'] = PV('2bma:m23.VAL')
        global_PVs['Focus'] = PV('2bma:m41.VAL')
        global_PVs['FocusName'] = PV('2bma:m41.DESC')
        
    elif params.station == '2-BM-B':   
        log.info('*** Running in station B:')
        # Sample stack motor pv's:
        global_PVs['SampleX'] = PV('2bmb:m63.VAL')
        global_PVs['SampleXSET'] = PV('2bmb:m63.SET')
        global_PVs['SampleY'] = PV('2bmb:m57.VAL') 
        global_PVs['SampleOmega'] = PV('2bmb:m100.VAL') # Aerotech ABR-150
        global_PVs['SampleOmegaAccl'] = PV('2bma:m100.ACCL') 
        global_PVs['SampleOmegaStop'] = PV('2bma:m100.STOP') 
        global_PVs['SampleOmegaSet'] = PV('2bma:m100.SET') 
        global_PVs['SampleOmegaVelo'] = PV('2bma:m100.VELO') 
        global_PVs['SampleXCent'] = PV('2bmb:m76.VAL') 
        global_PVs['SampleZCent'] = PV('2bmb:m77.VAL')

        # Set CCD stack motor PVs:
        global_PVs['Motor_CCD_Z'] = PV('2bmb:m31.VAL')

        # Set FlyScan
        global_PVs['FlyScanDelta'] = PV('2bmb:PSOFly:scanDelta')
        global_PVs['FlyStartPos'] = PV('2bmb:PSOFly:startPos')
        global_PVs['FlyEndPos'] = PV('2bmb:PSOFly:endPos')
        global_PVs['FlySlewSpeed'] = PV('2bmb:PSOFly:slewSpeed')
        global_PVs['FlyTaxi'] = PV('2bmb:PSOFly:taxi')
        global_PVs['FlyRun'] = PV('2bmb:PSOFly:fly')
        global_PVs['FlyScanControl'] = PV('2bmb:PSOFly:scanControl')
        global_PVs['FlyCalcProjections'] = PV('2bmb:PSOFly:numTriggers')
        global_PVs['OmegaArray'] = PV('2bmb:PSOFly:motorPos.AVAL')

        global_PVs['Focus'] = PV('2bmb:m78.VAL')
        global_PVs['FocusName'] = PV('2bmb:m78.DESC')

    else:
        log.error('*** %s is not a valid station' % params.station)

    # detector pv's
    if ((params.camera_ioc_prefix == '2bmbPG3:') or (params.camera_ioc_prefix == '2bmbSP1:')): 
    
        # general PV's
        global_PVs['Cam1SerialNumber'] = PV(params.camera_ioc_prefix + 'cam1:SerialNumber_RBV')
        global_PVs['Cam1ImageMode'] = PV(params.camera_ioc_prefix + 'cam1:ImageMode')
        global_PVs['Cam1ArrayCallbacks'] = PV(params.camera_ioc_prefix + 'cam1:ArrayCallbacks')
        global_PVs['Cam1AcquirePeriod'] = PV(params.camera_ioc_prefix + 'cam1:AcquirePeriod')
        global_PVs['Cam1TriggerMode'] = PV(params.camera_ioc_prefix + 'cam1:TriggerMode')
        global_PVs['Cam1SoftwareTrigger'] = PV(params.camera_ioc_prefix + 'cam1:SoftwareTrigger')  ### ask Mark is this is exposed in the medm screen
        global_PVs['Cam1AcquireTime'] = PV(params.camera_ioc_prefix + 'cam1:AcquireTime')
        global_PVs['Cam1FrameType'] = PV(params.camera_ioc_prefix + 'cam1:FrameType')
        global_PVs['Cam1NumImages'] = PV(params.camera_ioc_prefix + 'cam1:NumImages')
        global_PVs['Cam1Acquire'] = PV(params.camera_ioc_prefix + 'cam1:Acquire')
        global_PVs['Cam1AttributeFile'] = PV(params.camera_ioc_prefix + 'cam1:NDAttributesFile')
        global_PVs['Cam1FrameTypeZRST'] = PV(params.camera_ioc_prefix + 'cam1:FrameType.ZRST')
        global_PVs['Cam1FrameTypeONST'] = PV(params.camera_ioc_prefix + 'cam1:FrameType.ONST')
        global_PVs['Cam1FrameTypeTWST'] = PV(params.camera_ioc_prefix + 'cam1:FrameType.TWST')
        global_PVs['Cam1Display'] = PV(params.camera_ioc_prefix + 'image1:EnableCallbacks')

        global_PVs['Cam1SizeX'] = PV(params.camera_ioc_prefix + 'cam1:SizeX')
        global_PVs['Cam1SizeY'] = PV(params.camera_ioc_prefix + 'cam1:SizeY')
        global_PVs['Cam1SizeX_RBV'] = PV(params.camera_ioc_prefix + 'cam1:SizeX_RBV')
        global_PVs['Cam1SizeY_RBV'] = PV(params.camera_ioc_prefix + 'cam1:SizeY_RBV')
        global_PVs['Cam1MaxSizeX_RBV'] = PV(params.camera_ioc_prefix + 'cam1:MaxSizeX_RBV')
        global_PVs['Cam1MaxSizeY_RBV'] = PV(params.camera_ioc_prefix + 'cam1:MaxSizeY_RBV')
        global_PVs['Cam1PixelFormat_RBV'] = PV(params.camera_ioc_prefix + 'cam1:PixelFormat_RBV')

        global_PVs['Cam1Image'] = PV(params.camera_ioc_prefix + 'image1:ArrayData')

        # hdf5 writer PV's
        global_PVs['HDFAutoSave'] = PV(params.camera_ioc_prefix + 'HDF1:AutoSave')
        global_PVs['HDFDeleteDriverFile'] = PV(params.camera_ioc_prefix + 'HDF1:DeleteDriverFile')
        global_PVs['HDFEnableCallbacks'] = PV(params.camera_ioc_prefix + 'HDF1:EnableCallbacks')
        global_PVs['HDFBlockingCallbacks'] = PV(params.camera_ioc_prefix + 'HDF1:BlockingCallbacks')
        global_PVs['HDFFileWriteMode'] = PV(params.camera_ioc_prefix + 'HDF1:FileWriteMode')
        global_PVs['HDFNumCapture'] = PV(params.camera_ioc_prefix + 'HDF1:NumCapture')
        global_PVs['HDFCapture'] = PV(params.camera_ioc_prefix + 'HDF1:Capture')
        global_PVs['HDFCapture_RBV'] = PV(params.camera_ioc_prefix + 'HDF1:Capture_RBV')
        global_PVs['HDFFilePath'] = PV(params.camera_ioc_prefix + 'HDF1:FilePath')
        global_PVs['HDFFileName'] = PV(params.camera_ioc_prefix + 'HDF1:FileName')
        global_PVs['HDFFullFileName_RBV'] = PV(params.camera_ioc_prefix + 'HDF1:FullFileName_RBV')
        global_PVs['HDFFileTemplate'] = PV(params.camera_ioc_prefix + 'HDF1:FileTemplate')
        global_PVs['HDFArrayPort'] = PV(params.camera_ioc_prefix + 'HDF1:NDArrayPort')
        global_PVs['HDFFileNumber'] = PV(params.camera_ioc_prefix + 'HDF1:FileNumber')
        global_PVs['HDFXMLFileName'] = PV(params.camera_ioc_prefix + 'HDF1:XMLFileName')

        global_PVs['HDFQueueSize'] = PV(params.camera_ioc_prefix + 'HDF1:QueueSize')
        global_PVs['HDFQueueFree'] = PV(params.camera_ioc_prefix + 'HDF1:QueueFree')
                                                                      
        # proc1 PV's
        global_PVs['Image1EnableCallbacks'] = PV(params.camera_ioc_prefix + 'image1:EnableCallbacks')
        global_PVs['Proc1nableCallbacks'] = PV(params.camera_ioc_prefix + 'Proc1:EnableCallbacks')
        global_PVs['Proc1NDArrayPort'] = PV(params.camera_ioc_prefix + 'Proc1:NDArrayPort')
        global_PVs['Proc1EnableFilter'] = PV(params.camera_ioc_prefix + 'Proc1:EnableFilter')
        global_PVs['Proc1FilterType'] = PV(params.camera_ioc_prefix + 'Proc1:FilterType')
        global_PVs['Proc1Num_Filter'] = PV(params.camera_ioc_prefix + 'Proc1:NumFilter')
        global_PVs['Proc1ResetFilter'] = PV(params.camera_ioc_prefix + 'Proc1:ResetFilter')
        global_PVs['Proc1AutoResetFilter'] = PV(params.camera_ioc_prefix + 'Proc1:AutoResetFilter')
        global_PVs['Proc1FilterCallbacks'] = PV(params.camera_ioc_prefix + 'Proc1:FilterCallbacks')       

        global_PVs['Proc1EnableBackground'] = PV(params.camera_ioc_prefix + 'Proc1:EnableBackground')
        global_PVs['Proc1EnableFlatField'] = PV(params.camera_ioc_prefix + 'Proc1:EnableFlatField')
        global_PVs['Proc1EnableOffsetScale'] = PV(params.camera_ioc_prefix + 'Proc1:EnableOffsetScale')
        global_PVs['Proc1EnableLowClip'] = PV(params.camera_ioc_prefix + 'Proc1:EnableLowClip')
        global_PVs['Proc1EnableHighClip'] = PV(params.camera_ioc_prefix + 'Proc1:EnableHighClip')

    if (params.camera_ioc_prefix == '2bmbPG3:'):
        global_PVs['Cam1FrameRateOnOff'] = PV(params.camera_ioc_prefix + 'cam1:FrameRateOnOff')

    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        global_PVs['Cam1AcquireTimeAuto'] = PV(params.camera_ioc_prefix + 'cam1:AcquireTimeAuto')
        global_PVs['Cam1FrameRateOnOff'] = PV(params.camera_ioc_prefix + 'cam1:FrameRateEnable')

        global_PVs['Cam1TriggerSource'] = PV(params.camera_ioc_prefix + 'cam1:TriggerSource')
        global_PVs['Cam1TriggerOverlap'] = PV(params.camera_ioc_prefix + 'cam1:TriggerOverlap')
        global_PVs['Cam1ExposureMode'] = PV(params.camera_ioc_prefix + 'cam1:ExposureMode')
        global_PVs['Cam1TriggerSelector'] = PV(params.camera_ioc_prefix + 'cam1:TriggerSelector')
        global_PVs['Cam1TriggerActivation'] = PV(params.camera_ioc_prefix + 'cam1:TriggerActivation')
    
    else:
        log.error('Detector %s is not defined' % params.camera_ioc_prefix)
        return None        

    return global_PVs


def user_info_params_update_from_pv(global_PVs, params):

    params.proposal_title = global_PVs['ProposalTitle'].get(as_string=True)
    params.user_email = global_PVs['UserEmail'].get(as_string=True)
    params.user_badge = global_PVs['UserBadge'].get(as_string=True)
    params.user_last_name = global_PVs['UserLastName'].get(as_string=True)
    params.proposal_number = global_PVs['ProposalNumber'].get(as_string=True)
    params.user_institution = global_PVs['UserInstitution'].get(as_string=True)
    params.experiment_year_month = global_PVs['ExperimentYearMonth'].get(as_string=True)
    params.user_info_update = global_PVs['UserInfoUpdate'].get(as_string=True)


def image_pixel_size_pv_update(global_PVs, params):

    if (params.image_pixel_size is not None):
        global_PVs['ImagePixelSize'].put(params.image_pixel_size, wait=True)
    if (params.detector_pixel_size is not None):
        global_PVs['DetectorPixelSize'].put(params.detector_pixel_size, wait=True)
    if (params.camera_objective is not None):
        global_PVs['CameraObjective'].put(params.camera_objective, wait=True)


def open_shutters(global_PVs, params):

    log.info(' ')
    log.info('  *** open_shutters')
    if TESTING:
        # Logger(variableDict['LogFileName']).info('\x1b[2;30;43m' + '  *** WARNING: testing mode - shutters are deactivated during the scans !!!!' + '\x1b[0m')
        log.warning('  *** testing mode - shutters are deactivated during the scans !!!!')
    else:
        if params.station == '2-BM-A':
        # Use Shutter A
            if ShutterAisFast:
                global_PVs['ShutterAOpen'].put(1, wait=True)
                wait_pv(global_PVs['ShutterAMoveStatus'], ShutterAOpen_Value)
                time.sleep(3)                
                global_PVs['FastShutter'].put(1, wait=True)
                time.sleep(1)
                log.info('  *** open_shutter fast: Done!')
            else:
                global_PVs['ShutterAOpen'].put(1, wait=True)
                wait_pv(global_PVs['ShutterAMoveStatus'], ShutterAOpen_Value)
                time.sleep(3)
                log.info('  *** open_shutter A: Done!')
        elif params.station == '2-BM-B':
            global_PVs['ShutterBOpen'].put(1, wait=True)
            wait_pv(global_PVs['ShutterB_Move_Status'], ShutterBOpen_Value)
            log.info('  *** open_shutter B: Done!')
 

def close_shutters(global_PVs, params):

    log.info(' ')
    log.info('  *** close_shutters')
    if TESTING:
        # Logger(variableDict['LogFileName']).info('\x1b[2;30;43m' + '  *** WARNING: testing mode - shutters are deactivated during the scans !!!!' + '\x1b[0m')
        log.warning('  *** testing mode - shutters are deactivated during the scans !!!!')
    else:
        if params.station == '2-BM-A':
            if ShutterAisFast:
                global_PVs['FastShutter'].put(0, wait=True)
                time.sleep(1)
                log.info('  *** close_shutter fast: Done!')
            else:
                global_PVs['ShutterAClose'].put(1, wait=True)
                wait_pv(global_PVs['ShutterAMoveStatus'], ShutterAClose_Value)
                log.info('  *** close_shutter A: Done!')
        elif params.station == '2-BM-B':
            global_PVs['ShutterB_Close'].put(1, wait=True)
            wait_pv(global_PVs['ShutterB_Move_Status'], ShutterB_Close_Value)
            log.info('  *** close_shutter B: Done!')


def move_sample_out(global_PVs, params):

    log.info('      *** Sample out')
    if not (params.sample_move_freeze):
        if (params.flat_field_axis=="vertical"):
            log.info('      *** *** Move Sample Y out at: %f' % params.sample_out_y)
            global_PVs['SampleY'].put(str(params.sample_out_y), wait=True, timeout=1000.0)                
            if wait_pv(global_PVs['SampleY'], float(params.sample_out_y), 60) == False:
                log.error('SampleY did not move in properly')
                log.error(global_PVs['SampleY'].get())
        else:
            if (params.use_furnace):
                log.info('      *** *** Move Furnace Y out at: %f' % params.furnace_out_position)
                global_PVs['Motor_FurnaceY'].put(str(params.furnace_out_position), wait=True, timeout=1000.0)
                if wait_pv(global_PVs['Motor_FurnaceY'], float(params.furnace_out_position), 60) == False:
                    log.error('Motor_FurnaceY did not move in properly')
                    log.error(global_PVs['Motor_FurnaceY'].get())
            log.info('      *** *** Move Sample X out at: %f' % params.sample_out_x)
            global_PVs['SampleX'].put(str(params.sample_out_x), wait=True, timeout=1000.0)
            if wait_pv(global_PVs['SampleX'], float(params.sample_out_x), 60) == False:
                log.error('SampleX did not move in properly')
                log.error(global_PVs['SampleX'].get())
    else:
        log.info('      *** *** Sample Stack is Frozen')


def move_sample_in(global_PVs, params):

    log.info('      *** Sample in')
    if not (params.sample_move_freeze):
        if (params.flat_field_axis=="vertical"):
            log.info('      *** *** Move Sample Y in at: %f' % params.sample_in_y)
            global_PVs['SampleY'].put(str(params.sample_in_y), wait=True, timeout=1000.0)                
            if wait_pv(global_PVs['SampleY'], float(params.sample_in_y), 60) == False:
                log.error('SampleY did not move in properly')
                log.error(global_PVs['SampleY'].get())
        else:
            log.info('      *** *** Move Sample X in at: %f' % params.sample_in_x)
            global_PVs['SampleX'].put(str(params.sample_in_x), wait=True, timeout=1000.0)
            if wait_pv(global_PVs['SampleX'], float(params.sample_in_x), 60) == False:
                log.error('SampleX did not move in properly')
                log.error(global_PVs['SampleX'].get())
            if (params.use_furnace):
                log.info('      *** *** Move Furnace Y in at: %f' % params.furnace_in_position)
                global_PVs['Motor_FurnaceY'].put(str(params.furnace_in_position), wait=True, timeout=1000.0)
                if wait_pv(global_PVs['Motor_FurnaceY'], float(params.furnace_in_position), 60) == False:
                    log.error('Motor_FurnaceY did not move in properly')
                    log.error(global_PVs['Motor_FurnaceY'].get())
    else:
        log.info('      *** *** Sample Stack is Frozen')


def set_pso(global_PVs, params):

    acclTime = 1.0 * params.slew_speed/params.accl_rot
    scanDelta = abs(((float(params.rotation_end) - float(params.rotation_start))) / ((float(params.num_angles)) * float(params.recursive_filter_n_images)))

    log.info('  *** *** start_pos %f' % float(params.rotation_start))
    log.info('  *** *** end pos %f' % float(params.rotation_end))

    global_PVs['FlyStartPos'].put(float(params.rotation_start), wait=True)
    global_PVs['FlyEndPos'].put(float(params.rotation_end), wait=True)
    global_PVs['FlySlewSpeed'].put(params.slew_speed, wait=True)
    global_PVs['FlyScanDelta'].put(scanDelta, wait=True)
    time.sleep(3.0)

    calc_num_proj = global_PVs['FlyCalcProjections'].get()
    
    if calc_num_proj == None:
        log.error('  *** *** Error getting fly calculated number of projections!')
        calc_num_proj = global_PVs['FlyCalcProjections'].get()
        log.error('  *** *** Using %s instead of %s' % (calc_num_proj, params.num_angles))
    if calc_num_proj != int(params.num_angles):
        log.warning('  *** *** Changing number of projections from: %s to: %s' % (params.num_angles, int(calc_num_proj)))
        params.num_angles = int(calc_num_proj)
    log.info('  *** *** Number of projections: %d' % int(params.num_angles))
    log.info('  *** *** Fly calc triggers: %d' % int(calc_num_proj))
    global_PVs['FlyScanControl'].put('Standard')

    log.info(' ')
    log.info('  *** Taxi before starting capture')
    global_PVs['FlyTaxi'].put(1, wait=True)
    wait_pv(global_PVs['FlyTaxi'], 0)
    log.info('  *** Taxi before starting capture: Done!')