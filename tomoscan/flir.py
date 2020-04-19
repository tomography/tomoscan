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
Detector lib for Sector 2-BM  using Point Grey Grasshooper3 or FLIR Oryx cameras.
"""

import sys
import json
import time
import h5py
import traceback
import numpy as np

from tomoscan import aps2bm
from tomoscan import log

FrameTypeData = 0
FrameTypeDark = 1
FrameTypeWhite = 2

DetectorIdle = 0
DetectorAcquire = 1

Recursive_Filter_Type = 'RecursiveAve'

def init(global_PVs, params):
    if (params.camera_ioc_prefix == '2bmbPG3:'):   
        log.info('  *** init Point Grey camera')
        global_PVs['Cam1_TriggerMode'].put('Internal', wait=True)    # 
        global_PVs['Cam1_TriggerMode'].put('Overlapped', wait=True)  # sequence Internal / Overlapped / internal because of CCD bug!!
        global_PVs['Cam1_TriggerMode'].put('Internal', wait=True)    #
        global_PVs['Proc1_Filter_Callbacks'].put( 'Every array' )
        global_PVs['Cam1_ImageMode'].put('Single', wait=True)
        global_PVs['Cam1_Display'].put(1)
        global_PVs['Cam1_Acquire'].put(DetectorAcquire)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorAcquire, 2)
        global_PVs['Proc1_Callbacks'].put('Disable')
        global_PVs['Proc1_Filter_Enable'].put('Disable')
        global_PVs['HDF1_ArrayPort'].put('PG3')
        log.info('  *** init Point Grey camera: Done!')
    elif (params.camera_ioc_prefix == '2bmbSP1:'):   
        log.info(' ')                
        log.info('  *** init FLIR camera')
        log.info('  *** *** set detector to idle')
        global_PVs['Cam1_Acquire'].put(DetectorIdle)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, 2)
        log.info('  *** *** set detector to idle:  Done')
        # global_PVs['Proc1_Filter_Callbacks'].put( 'Every array', wait=True) # commented out to test if crash (ValueError: invalid literal for int() with base 0: 'Single') still occurs
        time.sleep(2) 
        log.info('  *** *** set trigger mode to Off')
        global_PVs['Cam1_TriggerMode'].put('Off', wait=True)    # 
        log.info('  *** *** set trigger mode to Off: done')
        time.sleep(7) 
        log.info('  *** *** set image mode to single')
        global_PVs['Cam1_ImageMode'].put('Single', wait=True)   # here is where it crashes with (ValueError: invalid literal for int() with base 0: 'Single') Added 7 s delay before
        log.info('  *** *** set image mode to single: done')
        log.info('  *** *** set cam display to 1')
        global_PVs['Cam1_Display'].put(1)
        log.info('  *** *** set cam display to 1: done')
        log.info('  *** *** set cam acquire')
        global_PVs['Cam1_Acquire'].put(DetectorAcquire)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorAcquire, 2) 
        log.info('  *** *** set cam acquire: done')
        if params.station == '2-BM-A':
            global_PVs['Cam1_AttributeFile'].put('flir2bmaDetectorAttributes.xml')
            global_PVs['HDF1_XMLFileName'].put('flir2bmaLayout.xml')           
        else: # Mona (B-station)
            global_PVs['Cam1_AttributeFile'].put('flir2bmbDetectorAttributes.xml', wait=True) 
            global_PVs['HDF1_XMLFileName'].put('flir2bmbLayout.xml', wait=True) 
        log.info('  *** init FLIR camera: Done!')


def set(global_PVs, params):

    fname = params.file_name
    # Set detectors
    if (params.camera_ioc_prefix == '2bmbPG3:'):   
        log.info(' ')
        log.info('  *** setup Point Grey')

        # mona runf always in B with PG camera
        global_PVs['Cam1_AttributeFile'].put('monaDetectorAttributes.xml', wait=True) 
        global_PVs['HDF1_XMLFileName'].put('monaLayout.xml', wait=True) 

        global_PVs['Cam1_ImageMode'].put('Multiple')
        global_PVs['Cam1_ArrayCallbacks'].put('Enable')
        #global_PVs['Image1_Callbacks'].put('Enable')
        global_PVs['Cam1_AcquirePeriod'].put(float(params.exposure_time))
        global_PVs['Cam1_AcquireTime'].put(float(params.exposure_time))
        # if we are using external shutter then set the exposure time
        global_PVs['Cam1_FrameRateOnOff'].put(0)

        wait_time_sec = int(params.exposure_time) + 5
        global_PVs['Cam1_TriggerMode'].put('Overlapped', wait=True) #Ext. Standard
        global_PVs['Cam1_NumImages'].put(1, wait=True)
        global_PVs['Cam1_Acquire'].put(DetectorAcquire)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorAcquire, 2)
        global_PVs['Cam1_SoftwareTrigger'].put(1)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, wait_time_sec)
        global_PVs['Cam1_Acquire'].put(DetectorAcquire)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorAcquire, 2)
        global_PVs['Cam1_SoftwareTrigger'].put(1)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, wait_time_sec)
        log.info('  *** setup Point Grey: Done!')

    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        log.info(' ')
        log.info('  *** setup FLIR camera')

        if params.station == '2-BM-A':
            global_PVs['Cam1_AttributeFile'].put('flir2bmaDetectorAttributes.xml')
            global_PVs['HDF1_XMLFileName'].put('flir2bmaLayout.xml')           
        else: # Mona (B-station)
            global_PVs['Cam1_AttributeFile'].put('flir2bmbDetectorAttributes.xml', wait=True) 
            global_PVs['HDF1_XMLFileName'].put('flir2bmbLayout.xml', wait=True) 

        global_PVs['Cam1_Acquire'].put(DetectorIdle)
        aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, 2)

        global_PVs['Cam1_TriggerMode'].put('Off', wait=True)
        global_PVs['Cam1_TriggerSource'].put('Line2', wait=True)
        global_PVs['Cam1_TriggerOverlap'].put('ReadOut', wait=True)
        global_PVs['Cam1_ExposureMode'].put('Timed', wait=True)
        global_PVs['Cam1_TriggerSelector'].put('FrameStart', wait=True)
        global_PVs['Cam1_TriggerActivation'].put('RisingEdge', wait=True)

        global_PVs['Cam1_ImageMode'].put('Multiple')
        global_PVs['Cam1_ArrayCallbacks'].put('Enable')
        #global_PVs['Image1_Callbacks'].put('Enable')
        #global_PVs['Cam1_AcquirePeriod'].put(float(params.exposure_time))
        global_PVs['Cam1_FrameRateOnOff'].put(0)
        global_PVs['Cam1_AcquireTimeAuto'].put('Off')

        global_PVs['Cam1_AcquireTime'].put(float(params.exposure_time))
        # if we are using external shutter then set the exposure time

        wait_time_sec = int(params.exposure_time) + 5

        global_PVs['Cam1_TriggerMode'].put('On', wait=True)
        log.info('  *** setup FLIR camera: Done!')
    
    else:
        log.error('Detector %s is not defined' % params.camera_ioc_prefix)
        return
    if fname is None:
        log.warning('  *** hdf_writer will not be configured')
    else:
        _setup_hdf_writer(global_PVs, params, fname)


def _setup_hdf_writer(global_PVs, params, fname=None):

    if (params.camera_ioc_prefix == '2bmbPG3:') or (params.camera_ioc_prefix == '2bmbSP1:'):   
        # setup Point Grey hdf writer PV's
        log.info('  ')
        log.info('  *** setup hdf_writer')
        _setup_frame_type(global_PVs, params)
        if params.recursive_filter == True:
            log.info('    *** Recursive Filter Enabled')
            global_PVs['Proc1_Enable_Background'].put('Disable', wait=True)
            global_PVs['Proc1_Enable_FlatField'].put('Disable', wait=True)
            global_PVs['Proc1_Enable_Offset_Scale'].put('Disable', wait=True)
            global_PVs['Proc1_Enable_Low_Clip'].put('Disable', wait=True)
            global_PVs['Proc1_Enable_High_Clip'].put('Disable', wait=True)

            global_PVs['Proc1_Callbacks'].put('Enable', wait=True)
            global_PVs['Proc1_Filter_Enable'].put('Enable', wait=True)
            global_PVs['HDF1_ArrayPort'].put('PROC1', wait=True)
            global_PVs['Proc1_Filter_Type'].put(Recursive_Filter_Type, wait=True)
            global_PVs['Proc1_Num_Filter'].put(int(params.recursive_filter_n_images), wait=True)
            global_PVs['Proc1_Reset_Filter'].put(1, wait=True)
            global_PVs['Proc1_AutoReset_Filter'].put('Yes', wait=True)
            global_PVs['Proc1_Filter_Callbacks'].put('Array N only', wait=True)
            log.info('    *** Recursive Filter Enabled: Done!')
        else:
            global_PVs['Proc1_Filter_Enable'].put('Disable')
            global_PVs['HDF1_ArrayPort'].put(global_PVs['Proc1_ArrayPort'].get())
        global_PVs['HDF1_AutoSave'].put('Yes')
        global_PVs['HDF1_DeleteDriverFile'].put('No')
        global_PVs['HDF1_EnableCallbacks'].put('Enable')
        global_PVs['HDF1_BlockingCallbacks'].put('No')

        # if (params.recursive_filter == False):
        #     params.recursive_filter_n_images = 1

        totalProj = ((int(params.num_projections / params.recursive_filter_n_images)) + int(params.num_dark_images) + \
                        int(params.num_white_images))

        global_PVs['HDF1_NumCapture'].put(totalProj)
        global_PVs['HDF1_FileWriteMode'].put(str(params.file_write_mode), wait=True)
        if fname is not None:
            global_PVs['HDF1_FileName'].put(str(fname), wait=True)
        global_PVs['HDF1_Capture'].put(1)
        aps2bm.wait_pv(global_PVs['HDF1_Capture'], 1)
        log.info('  *** setup hdf_writer: Done!')
    else:
        log.error('Detector %s is not defined' % params.camera_ioc_prefix)
        return


def _setup_frame_type(global_PVs, params):
    global_PVs['Cam1_FrameTypeZRST'].put('/exchange/data')
    global_PVs['Cam1_FrameTypeONST'].put('/exchange/data_dark')
    global_PVs['Cam1_FrameTypeTWST'].put('/exchange/data_white')



def acquire(global_PVs, params):
    theta = []

    # Estimate the time needed for the flyscan
    angular_range =  params.sample_rotation_end -  params.sample_rotation_start
    flyscan_time_estimate = angular_range / params.slew_speed

    # log.info(' ')
    log.warning('  *** Fly Scan Time Estimate: %4.2f minutes' % (flyscan_time_estimate/60.))

    global_PVs['Cam1_FrameType'].put(FrameTypeData, wait=True)
    time.sleep(2)    

    # global_PVs['Cam1_AcquireTime'].put(float(params.exposure_time) )

    if (params.recursive_filter == False):
        params.recursive_filter_n_images = 1

    num_images = int(params.num_projections)  * params.recursive_filter_n_images   
    global_PVs['Cam1_NumImages'].put(num_images, wait=True)


    # Set detectors
    if (params.camera_ioc_prefix == '2bmbPG3:'):   
        global_PVs['Cam1_TriggerMode'].put('Overlapped', wait=True)
    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        global_PVs['Cam1_TriggerMode'].put('On', wait=True)

    # start acquiring
    global_PVs['Cam1_Acquire'].put(DetectorAcquire)
    aps2bm.wait_pv(global_PVs['Cam1_Acquire'], 1)

    log.info(' ')
    log.info('  *** Fly Scan: Start!')
    global_PVs['Fly_Run'].put(1, wait=True)
    # wait for acquire to finish 
    aps2bm.wait_pv(global_PVs['Fly_Run'], 0)

    # if the fly scan wait times out we should call done on the detector
#    if aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, flyscan_time_estimate) == False:
    if aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, 5) == False:
        global_PVs['Cam1_Acquire'].put(DetectorIdle)
        #  got error here once when missing 100s of frames: aps2bm.wait_pv( 2bmbSP1:cam1:Acquire 0 5 ) reached max timeout. Return False
    
    log.info('  *** Fly Scan: Done!')
    # Set trigger mode to internal for post dark and white
    if (params.camera_ioc_prefix == '2bmbPG3:'):   
        global_PVs['Cam1_TriggerMode'].put('Internal')
    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        global_PVs['Cam1_TriggerMode'].put('Off', wait=True)


    theta = global_PVs['Theta_Array'].get(count=int(params.num_projections))
    if (params.recursive_filter_n_images > 1):
        theta = np.mean(theta.reshape(-1, params.recursive_filter_n_images), axis=1)
    
    return theta
            

def acquire_flat(global_PVs, params):
    log.info('      *** White Fields')
   
    global_PVs['Cam1_ImageMode'].put('Multiple')
    global_PVs['Cam1_FrameType'].put(FrameTypeWhite)             

    if (params.camera_ioc_prefix == '2bmbPG3:'):
        global_PVs['Cam1_TriggerMode'].put('Overlapped')
    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        global_PVs['Cam1_TriggerMode'].put('Off', wait=True)
        
    # Set detectors
    if (params.camera_ioc_prefix == '2bmbPG3:'):   
        wait_time_sec = int(params.exposure_time) + 5
        global_PVs['Cam1_NumImages'].put(1)

        for i in range(int(params.num_white_images) * params.recursive_filter_n_images):
            global_PVs['Cam1_Acquire'].put(DetectorAcquire)
            time.sleep(0.1)
            aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorAcquire, 2)
            time.sleep(0.1)
            global_PVs['Cam1_SoftwareTrigger'].put(1, wait=True)
            time.sleep(0.1)
            aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, wait_time_sec)
            time.sleep(0.1)

    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        wait_time_sec = float(params.num_white_images) * float(params.exposure_time) + 60.0
        global_PVs['Cam1_NumImages'].put(int(params.num_white_images))
        global_PVs['Cam1_Acquire'].put(DetectorAcquire, wait=True, timeout=5.0) # it was 1000.0

        # time.sleep(0.1)
        if aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, wait_time_sec) == False: # adjust wait time
            global_PVs['Cam1_Acquire'].put(DetectorIdle)
    
    log.info('      *** White Fields: Done!')


def acquire_dark(global_PVs, params):
    log.info("      *** Dark Fields") 
    global_PVs['Cam1_ImageMode'].put('Multiple')
    global_PVs['Cam1_FrameType'].put(FrameTypeDark)             

    if (params.camera_ioc_prefix == '2bmbPG3:'):
        global_PVs['Cam1_TriggerMode'].put('Overlapped')
    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        global_PVs['Cam1_TriggerMode'].put('Off', wait=True)
        
    # Set detectors
    if (params.camera_ioc_prefix == '2bmbPG3:'):   

        wait_time_sec = int(params.exposure_time) + 5
        global_PVs['Cam1_NumImages'].put(1)

        for i in range(int(params.num_dark_images) * params.recursive_filter_n_images):
            global_PVs['Cam1_Acquire'].put(DetectorAcquire)
            time.sleep(0.1)
            aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorAcquire, 2)
            time.sleep(0.1)
            global_PVs['Cam1_SoftwareTrigger'].put(1, wait=True)
            time.sleep(0.1)
            aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, wait_time_sec)
            time.sleep(0.1)
        aps2bm.wait_pv(global_PVs["HDF1_Capture_RBV"], 0, 600)

    elif (params.camera_ioc_prefix == '2bmbSP1:'):
        wait_time_sec = float(params.num_dark_images) * float(params.exposure_time) + 60.0
        global_PVs['Cam1_NumImages'].put(int(params.num_dark_images))
        global_PVs['Cam1_Acquire'].put(DetectorAcquire, wait=True, timeout=5.0) # it was 1000.0
        if aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, wait_time_sec) == False: # adjust wait time
            global_PVs['Cam1_Acquire'].put(DetectorIdle)

    log.info('      *** Dark Fields: Done!')
    log.info('  *** Acquisition: Done!')        


def checkclose_hdf(global_PVs, params):

    buffer_queue = global_PVs['HDF1_QueueSize'].get() - global_PVs['HDF1_QueueFree'].get()
    # wait_on_hdd = 10
    frate = 55.0
    wait_on_hdd = buffer_queue / frate + 10
    # wait_on_hdd = (global_PVs['HDF1_QueueSize'].get() - global_PVs['HDF1_QueueFree'].get()) / 55.0 + 10
    log.info('  *** Buffer Queue (frames): %d ' % buffer_queue)
    log.info('  *** Wait HDD (s): %f' % wait_on_hdd)
    if aps2bm.wait_pv(global_PVs["HDF1_Capture_RBV"], 0, wait_on_hdd) == False: # needs to wait for HDF plugin queue to dump to disk
        global_PVs["HDF1_Capture"].put(0)
        log.info('  *** File was not closed => forced to close')
        log.info('      *** before %d' % global_PVs["HDF1_Capture_RBV"].get())
        aps2bm.wait_pv(global_PVs["HDF1_Capture_RBV"], 0, 5) 
        log.info('      *** after %d' % global_PVs["HDF1_Capture_RBV"].get())
        if (global_PVs["HDF1_Capture_RBV"].get() == 1):
            log.error('  *** ERROR HDF FILE DID NOT CLOSE; add_theta will fail')


def add_theta(global_PVs, params, theta_arr):
    log.info(' ')
    log.info('  *** add_theta')
    
    fullname = global_PVs['HDF1_FullFileName_RBV'].get(as_string=True)
    try:
        hdf_f = h5py.File(fullname, mode='a')
        if theta_arr is not None:
            theta_ds = hdf_f.create_dataset('/exchange/theta', (len(theta_arr),))
            theta_ds[:] = theta_arr[:]
        hdf_f.close()
        log.info('  *** add_theta: Done!')
    except:
        traceback.print_exc(file=sys.stdout)
        log.info('  *** add_theta: Failed accessing: %s' % fullname)


def take_image(global_PVs, params):

    log.info('  ***  *** taking a single image')
   
    nRow = global_PVs['Cam1_SizeY_RBV'].get()
    nCol = global_PVs['Cam1_SizeX_RBV'].get()

    image_size = nRow * nCol

    global_PVs['Cam1_NumImages'].put(1, wait=True)

    global_PVs['Cam1_TriggerMode'].put('Off', wait=True)
    wait_time_sec = int(params.exposure_time) + 5

    global_PVs['Cam1_Acquire'].put(DetectorAcquire, wait=True, timeout=1000.0)
    time.sleep(0.1)
    if aps2bm.wait_pv(global_PVs['Cam1_Acquire'], DetectorIdle, wait_time_sec) == False: # adjust wait time
        global_PVs['Cam1_Acquire'].put(DetectorIdle)
    
    # Get the image loaded in memory
    img_vect = global_PVs['Cam1_Image'].get(count=image_size)
    img = np.reshape(img_vect,[nRow, nCol])

    pixelFormat = global_PVs['Cam1PixelFormat_RBV'].get(as_string=True)
    if (pixelFormat == "Mono16"):
        pixel_f = 16
    elif (pixelFormat == "Mono8"):
        pixel_f = 8
    else:
        log.error('  ***  *** bit %s format not supported' % pixelFormat)
        exit()
    img_uint = np.mod(img, 2**pixel_f)

    return img_uint


def take_flat(global_PVs, params):

    log.info('  ***  *** acquire white')
    return take_image(global_PVs, params)


def take_dark(global_PVs, params):
    
    log.info('  ***  *** acquire dark')
    return take_image(global_PVs, params)


def take_dark_and_white(global_PVs, params):
    aps2bm.close_shutters(global_PVs, params)
    dark_field = take_dark(global_PVs, params)
    # plot(dark_field)

    aps2bm.open_shutters(global_PVs, params)
    aps2bm.move_sample_out(global_PVs, params)
    white_field = take_flat(global_PVs, params)
    # plot(white_field)

    aps2bm.move_sample_in(global_PVs, params)

    return dark_field, white_field