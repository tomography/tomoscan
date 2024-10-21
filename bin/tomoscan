#!/usr/bin/env python

"""
tomoscan-cli
"""

import os
import re
import sys
import argparse
import time
import shutil
import pathlib
import json
import numpy as np
from datetime import datetime

from tomoscan import config, __version__
from tomoscan import log

from epics import PV
import epics

def init_PVs(tomoscan_prefix):
    
    ts_pvs = {}
    file_plugin_prefix              = epics.caget(tomoscan_prefix + 'FilePluginPVPrefix')    
    
    sample_x_pv_name                = PV(tomoscan_prefix + 'SampleXPVName').value
    sample_y_pv_name                = PV(tomoscan_prefix + 'SampleYPVName').value
    ts_pvs['SampleX']               = PV(sample_x_pv_name)
    ts_pvs['SampleY']               = PV(sample_y_pv_name)

    ts_pvs['StartScan']             = PV(tomoscan_prefix + 'StartScan')
    ts_pvs['ServerRunning']         = PV(tomoscan_prefix + 'ServerRunning')
    ts_pvs['ScanStatus']            = PV(tomoscan_prefix + 'ScanStatus')
    ts_pvs['SampleName']            = PV(tomoscan_prefix + 'SampleName')

    ts_pvs['FileName']              = PV(tomoscan_prefix + 'FileName')
    ts_pvs['FileTemplate']          = PV(file_plugin_prefix + 'FileTemplate')
    ts_pvs['FileNumber']            = PV(file_plugin_prefix + 'FileNumber')

    ts_pvs['RotationStart']         = PV(tomoscan_prefix + 'RotationStart')  
    ts_pvs['RotationStep']          = PV(tomoscan_prefix + 'RotationStep')  
    ts_pvs['NumAngles']             = PV(tomoscan_prefix + 'NumAngles')  
    ts_pvs['ReturnRotation']        = PV(tomoscan_prefix + 'ReturnRotation')  
    ts_pvs['NumDarkFields']         = PV(tomoscan_prefix + 'NumDarkFields')  
    ts_pvs['DarkFieldMode']         = PV(tomoscan_prefix + 'DarkFieldMode')  
    ts_pvs['DarkFieldValue']        = PV(tomoscan_prefix + 'DarkFieldValue')  
    ts_pvs['NumFlatFields']         = PV(tomoscan_prefix + 'NumFlatFields')
    ts_pvs['FlatFieldAxis']         = PV(tomoscan_prefix + 'FlatFieldAxis')
    ts_pvs['FlatFieldMode']         = PV(tomoscan_prefix + 'FlatFieldMode')
    ts_pvs['FlatFieldValue']        = PV(tomoscan_prefix + 'FlatFieldValue')  
    ts_pvs['FlatExposureTime']      = PV(tomoscan_prefix + 'FlatExposureTime')  
    ts_pvs['DifferentFlatExposure'] = PV(tomoscan_prefix + 'DifferentFlatExposure')
    ts_pvs['SampleInX']             = PV(tomoscan_prefix + 'SampleInX')
    ts_pvs['SampleOutX']            = PV(tomoscan_prefix + 'SampleOutX')  
    ts_pvs['SampleInY']             = PV(tomoscan_prefix + 'SampleInY')
    ts_pvs['SampleOutY']            = PV(tomoscan_prefix + 'SampleOutY')  
    ts_pvs['SampleOutAngleEnable']  = PV(tomoscan_prefix + 'SampleOutAngleEnable') 
    ts_pvs['SampleOutAngle']        = PV(tomoscan_prefix + 'SampleOutAngle')  
    ts_pvs['ScanType']              = PV(tomoscan_prefix + 'ScanType')
    ts_pvs['FlipStitch']            = PV(tomoscan_prefix + 'FlipStitch')
    ts_pvs['ExposureTime']          = PV(tomoscan_prefix + 'ExposureTime')

    return ts_pvs

def init(args):

    if not os.path.exists(str(args.config)):
        config.write(args.config)
    else:
        log.error("{0} already exists".format(args.config))

    ts_pvs = init_PVs(args.tomoscan_prefix)
    scan_dict = {}

    RotationStart         = ts_pvs['RotationStart'].get() 
    RotationStep          = ts_pvs['RotationStep'].get()  
    NumAngles             = ts_pvs['NumAngles'].get() 
    ReturnRotation        = ts_pvs['ReturnRotation'].get() 
    NumDarkFields         = ts_pvs['NumDarkFields'].get() 
    DarkFieldMode         = ts_pvs['DarkFieldMode'].get(as_string=True) 
    DarkFieldValue        = ts_pvs['DarkFieldValue'].get() 
    NumFlatFields         = ts_pvs['NumFlatFields'].get() 
    FlatFieldAxis         = ts_pvs['FlatFieldAxis'].get(as_string=True) 
    FlatFieldMode         = ts_pvs['FlatFieldMode'].get(as_string=True) 
    FlatFieldValue        = ts_pvs['FlatFieldValue'].get() 
    FlatExposureTime      = ts_pvs['FlatExposureTime'].get() 
    DifferentFlatExposure = ts_pvs['DifferentFlatExposure'].get(as_string=True) 
    SampleInX             = ts_pvs['SampleInX'].get() 
    SampleOutX            = ts_pvs['SampleOutX'].get() 
    SampleInY             = ts_pvs['SampleInY'].get() 
    SampleOutY            = ts_pvs['SampleOutY'].get() 
    SampleOutAngleEnable  = ts_pvs['SampleOutAngleEnable'].get(as_string=True) 
    SampleOutAngle        = ts_pvs['SampleOutAngle'].get() 
    ScanType              = ts_pvs['ScanType'].get(as_string=True) 
    FlipStitch            = ts_pvs['FlipStitch'].get(as_string=True) 
    ExposureTime          = ts_pvs['ExposureTime'].get()

    for x in range(args.num_scans):
        key = str(x).zfill(3)
        scan_dict[key] =  {'SampleX' : 0.0,  
                           'SampleY' : 0.0,  
                           'RotationStart'         : RotationStart, 
                           'RotationStep'          : RotationStep,  
                           'NumAngles'             : NumAngles, 
                           'ReturnRotation'        : ReturnRotation, 
                           'NumDarkFields'         : NumDarkFields, 
                           'DarkFieldMode'         : DarkFieldMode, 
                           'DarkFieldValue'        : DarkFieldValue, 
                           'NumFlatFields'         : NumFlatFields, 
                           'FlatFieldAxis'         : FlatFieldAxis, 
                           'FlatFieldMode'         : FlatFieldMode, 
                           'FlatFieldValue'        : FlatFieldValue, 
                           'FlatExposureTime'      : FlatExposureTime, 
                           'DifferentFlatExposure' : DifferentFlatExposure, 
                           'SampleInX'             : SampleInX, 
                           'SampleOutX'            : SampleOutX, 
                           'SampleInY'             : SampleInY, 
                           'SampleOutY'            : SampleOutY, 
                           'SampleOutAngleEnable'  : SampleOutAngleEnable, 
                           'SampleOutAngle'        : SampleOutAngle, 
                           'ScanType'              : ScanType, 
                           'FlipStitch'            : FlipStitch, 
                           'ExposureTime'          : ExposureTime
                           }

    with open(args.scan_file, 'w') as fp:
        json.dump(scan_dict, fp, indent=4, sort_keys=True)

    log.info('For arbitrary scans location custormize (SampleX, SampleY) in {0}'.format(args.scan_file))

def run_status(args):
    config.show_config(args)

def run_single(args):
    args.scan_type = 'Single'
    run_scan(args)
    config.write(args.config, args, sections=config.SINGLE_SCAN_PARAMS)

def run_vertical(args):
    args.scan_type = 'Vertical'
    run_scan(args)
    config.write(args.config, args, sections=config.VERTICAL_SCAN_PARAMS)

def run_horizontal(args):
    args.scan_type = 'Horizontal'
    run_scan(args)
    config.write(args.config, args, sections=config.HORIZONTAL_SCAN_PARAMS)

def run_mosaic(args):
    args.scan_type = 'Mosaic'
    run_scan(args)
    config.write(args.config, args, sections=config.MOSAIC_SCAN_PARAMS)

def run_energy(args):
    args.scan_type = 'Energy'
    run_scan(args)
    config.write(args.config, args, sections=config.ENERGY_SCAN_PARAMS)    

def run_file(args):

    args.scan_type = 'File'
    run_scan(args)
    config.write(args.config, args, sections=config.ENERGY_SCAN_PARAMS)    


def run_scan(args):
    
    ts_pvs = init_PVs(args.tomoscan_prefix)

    if ts_pvs['ServerRunning'].get():
        if ts_pvs['ScanStatus'].get(as_string=True) == 'Scan complete':
            log.warning('%s scan start', args.scan_type)
            ts_pvs['ScanType'].put(args.scan_type, wait=True)
            if (args.sleep_steps >= 1) and (args.sleep == True):
                log.warning('running %d x %2.2fs sleep scans', args.sleep_steps, args.sleep_time)
                tic =  time.time()
                for ii in np.arange(0, args.sleep_steps, 1):
                    log.warning('sleep start scan %d/%d', ii, args.sleep_steps-1)
                    scan(args, ts_pvs)
                    if (args.sleep_steps+1)!=(ii+1):
                        if (args.in_situ):
                            in_situ_set_value = args.in_situ_start + (ii) * args.in_situ_step_size
                            log.error('in-situ set value: %3.3f ', in_situ_set_value)
                            # set in-situ PV
                            # wait on in-situ read back value
                        log.warning('wait (s): %s ' , str(args.sleep_time))
                        time.sleep(args.sleep_time)
                dtime = (time.time() - tic)/60.
                log.info('sleep scans time: %3.3f minutes', dtime)
                log.warning('sleep scan end')
            else:
                scan(args, ts_pvs)
            log.warning('%s scan end', args.scan_type)
            ts_pvs['ScanType'].put('Single', wait=True)
        else:
            log.error('Server %s is busy. Please run a scan manually first.', args.tomoscan_prefix)
    else:
        log.error('Server %s is not runnig', args.tomoscan_prefix)

def scan(args, ts):

    tic_01 =  time.time()
    flat_field_axis = ts['FlatFieldAxis'].get(as_string=True)
    flat_field_mode = ts['FlatFieldMode'].get(as_string=True)
    if (args.scan_type == 'Single'):
        single_scan(args, ts)
    elif (args.scan_type == 'File'):
        file_scan(args, ts)   
    elif (args.scan_type == 'Energy'):
        energy_scan(args, ts)        
    elif (args.scan_type == 'Mosaic'):
        start_y = args.vertical_start
        step_size_y = args.vertical_step_size  
        steps_y = args.vertical_steps
        end_y = start_y + (step_size_y * steps_y) 

        start_x = args.horizontal_start
        step_size_x = args.horizontal_step_size
        steps_x = args.horizontal_steps  
        end_x = start_x + (step_size_x * steps_x)

        log.info('vertical positions (mm): %s', np.linspace(start_y, end_y, steps_y, endpoint=False))
        for i in np.linspace(start_y, end_y, steps_y, endpoint=False):
            log.warning('%s stage start position: %3.3f mm', 'SampleInY', i)
            if flat_field_axis in ('X') or flat_field_mode == 'None':
                pv_y = "SampleY"
            else:
                pv_y = "SampleInY"
            ts[pv_y].put(i, wait=True, timeout=600)
            log.info('horizontal positions (mm): %s', np.linspace(start_x, end_x, steps_x, endpoint=False))
            for j in np.linspace(start_x, end_x, steps_x, endpoint=False):
                log.warning('%s stage start position: %3.3f mm', 'SampleInX', j)
                if flat_field_axis in ('Y') or flat_field_mode == 'None':
                    pv_x = "SampleX"
                else:
                    pv_x = "SampleInX"
                ts[pv_x].put(j, wait=True, timeout=600)
                single_scan(args, ts)
        dtime = (time.time() - tic_01)/60.
        log.info('%s scan time: %3.3f minutes', args.scan_type, dtime)
    else:
        if (args.scan_type == 'Horizontal'):
            start = args.horizontal_start
            step_size = args.horizontal_step_size       
            steps = args.horizontal_steps
            end = start + (step_size * steps)
            log.info('horizontal positions (mm): %s', np.linspace(start, end, steps, endpoint=False))
            if flat_field_axis in ('Y') or flat_field_mode == 'None':
                pv = "SampleX"
            else:
                pv = "SampleInX"
        elif (args.scan_type == 'Vertical'):
            start = args.vertical_start
            step_size = args.vertical_step_size
            steps = args.vertical_steps
            end = start + (step_size * steps)
            log.info('vertical positions (mm): %s', np.linspace(start, end, steps, endpoint=False))
            if flat_field_axis in ('X') or flat_field_mode == 'None':
                pv = "SampleY"
            else:
                pv = "SampleInY"
        for i in np.linspace(start, end, steps, endpoint=False):
            log.warning('%s stage start position: %3.3f mm', pv, i)
            ts[pv].put(i, wait=True, timeout=600)
            single_scan(args, ts)
        dtime = (time.time() - tic_01)/60.
        log.info('%s scan time: %3.3f minutes', args.scan_type, dtime)

    ts['ScanType'].put('Single', wait=True)

def single_scan(args, ts):

    tic_01 =  time.time()
    log.info('single scan start')
    if args.testing:
        log.warning('testing mode')
    else: 
        ts['StartScan'].put(1, wait=True, timeout=360000) # -1 - no timeout means timeout=0
    dtime = (time.time() - tic_01)/60.
    log.info('single scan time: %3.3f minutes', dtime)

def energy_scan(args, ts):
    
    tic_01 =  time.time()
    log.info('energy scan start')
    
    ts['StartEnergyChange'] = PV(args.tomoscan_prefix + 'StartEnergyChange')    
    ts['Energy'] = PV(args.tomoscan_prefix + 'Energy')    
    
    energies = np.load(args.file_energies)    
    
    # read pvs for 2 energies
    pvs1, pvs2, vals1, vals2 = [],[],[],[]
    with open(args.file_params1,'r') as fid:
        for pv_val in fid.readlines():
            pv, val = pv_val[:-1].split(' ')
            pvs1.append(pv)
            vals1.append(float(val))
    with open(args.file_params2,'r') as fid:
        for pv_val in fid.readlines():
            pv, val = pv_val[:-1].split(' ')
            pvs2.append(pv)
            vals2.append(float(val))                    
    
    for k in range(len(pvs1)):
        if(pvs1[k]!=pvs2[k]):
            log.error("Inconsitent files with PVs")
            exit(1)

    if(np.abs(vals2[0]-vals1[0])<0.001):            
        log.error("Energies in params files should be different")
        exit(1)

    # energy scan
    print(energies)
    energies=energies/1000.0
    for energy in energies:               
        log.info("energy %.3f eV", energy)                    
        # interpolate values
        vals = []                     
        for k in range(len(pvs1)):
            vals.append(vals1[k]+(energy-vals1[0])*(vals2[k]-vals1[k])/(vals2[0]-vals1[0]))               
        if args.testing:
            log.warning('testing mode')
        else:           
            # set new pvs  
            for k in range(1,len(pvs1)):# skip energy line
                if(pvs1[k]=="32idcTXM:mxv:c1:m6.VAL"):
                    log.info('old Camera Z %3.3f', PV(pvs1[k]).get())
                    PV(pvs1[k]).put(vals[k],wait=True)                                                        
                    log.info('new Camera Z %3.3f', PV(pvs1[k]).get())
                if(pvs1[k]=="32idcTXM:mcs:c2:m3.VAL"):
                    log.info('old FZP Z %3.3f', PV(pvs1[k]).get())
                    PV(pvs1[k]).put(vals[k],wait=True)
                    log.info('new FZP Z %3.3f', PV(pvs1[k]).get())
                if(pvs1[k]=="32idcTXM:mcs:c2:m1.VAL"):
                    log.info('old FZP X %3.3f', PV(pvs1[k]).get())
                    PV(pvs1[k]).put(vals[k],wait=True)
                    log.info('new FZP X %3.3f', PV(pvs1[k]).get())
                                    
            # set new energy
            ts['Energy'].put(energy)
            time.sleep(1)
            # change energy via tomoscan
            ts['StartEnergyChange'].put(1)#,timeout=3600)
            log.warning('wait 10s to finalize energy changes')
            time.sleep(10)
            log.warning('start scan')
            # start scan
            ts['StartScan'].put(1, wait=True, timeout=360000) # -1 - no timeout means timeout=0                
            
    dtime = (time.time() - tic_01)/60.
    log.info('energy scan time: %3.3f minutes', dtime)
    ts['ScanType'].put('Single', wait=True)


def file_scan(args, ts):

    tic_01 =  time.time()
    log.info('file scan start')

    try:
        with open(args.scan_file) as json_file:
            scan_dict = json.load(json_file)
    except FileNotFoundError:
        log.error('File %s not found', args.scan_file)
        exit()
    except:
        log.error('File %s is not correcly formatted', args.scan_file)
        exit()
    flat_field_axis = ts['FlatFieldAxis'].get(as_string=True)
    flat_field_mode = ts['FlatFieldMode'].get(as_string=True)

    for key, value in scan_dict.items():


        ts['SampleX'].put(value['SampleX'], wait=True)
        ts['SampleY'].put(value['SampleY'], wait=True)
        ts['RotationStart'].put(value['RotationStart'], wait=True) 
        ts['RotationStep'].put(value['RotationStep'], wait=True)
        ts['NumAngles'].put(value['NumAngles'], wait=True) 
        ts['ReturnRotation'].put(value['ReturnRotation'], wait=True) 
        ts['NumDarkFields'].put(value['NumDarkFields'], wait=True) 
        ts['DarkFieldMode'].put(value['DarkFieldMode'], wait=True) 
        ts['DarkFieldValue'].put(value['DarkFieldValue'], wait=True) 
        ts['NumFlatFields'].put(value['NumFlatFields'], wait=True) 
        ts['FlatFieldAxis'].put(value['FlatFieldAxis'], wait=True) 
        ts['FlatFieldMode'].put(value['FlatFieldMode'], wait=True) 
        ts['FlatFieldValue'].put(value['FlatFieldValue'], wait=True) 
        ts['FlatExposureTime'].put(value['FlatExposureTime'], wait=True) 
        ts['DifferentFlatExposure'].put(value['DifferentFlatExposure'], wait=True) 
        ts['SampleInX'].put(value['SampleInX'], wait=True) 
        ts['SampleOutX'].put(value['SampleOutX'], wait=True) 
        ts['SampleInY'].put(value['SampleInY'], wait=True) 
        ts['SampleOutY'].put(value['SampleOutY'], wait=True) 
        ts['SampleOutAngleEnable'].put(value['SampleOutAngleEnable'], wait=True) 
        ts['SampleOutAngle'].put(value['SampleOutAngle'], wait=True) 
        ts['ScanType'].put(value['ScanType'], wait=True) 
        ts['FlipStitch'].put(value['FlipStitch'], wait=True) 
        ts['ExposureTime'].put(value['ExposureTime'], wait=True)

        log.warning('Scan key/number: %s ', key)
        log.warning('%s stage position: %3.3f mm', 'Sample Y', value['SampleY'])
        log.warning('%s stage position: %3.3f mm', 'Sample X', value['SampleX'])
        if flat_field_axis in ('X') or flat_field_mode == 'None':
            pv_y = "SampleY"
        else:
            pv_y = "SampleInY"
        ts[pv_y].put(value['SampleY'], wait=True, timeout=600)
        if flat_field_axis in ('Y') or flat_field_mode == 'None':
            pv_x = "SampleX"
        else:
            pv_x = "SampleInX"
        ts[pv_x].put(value['SampleX'], wait=True, timeout=600)
        # single_scan(args, ts)
        # config.write(args.config, args, sections=config.SINGLE_SCAN_PARAMS)

    dtime = (time.time() - tic_01)/60.
    log.info('file scan time: %3.3f minutes', dtime)
    ts['ScanType'].put('Single', wait=True)

def main():
    # set logs directory
    home = os.path.expanduser("~")
    logs_home = home + '/logs/'
    # make sure logs directory exists
    if not os.path.exists(logs_home):
        os.makedirs(logs_home)
    # setup logger
    lfname = logs_home + 'tomoscan_' + datetime.strftime(datetime.now(), "%Y-%m-%d_%H:%M:%S") + '.log'
    log.setup_custom_logger(lfname)

    parser = argparse.ArgumentParser()
    parser.add_argument('--config', **config.SECTIONS['general']['config'])
    parser.add_argument('--version', action='version',
                        version='%(prog)s {}'.format(__version__))

    init_param       = config.INIT_PARAMS
    single_param     = config.SINGLE_SCAN_PARAMS
    vertical_param   = config.VERTICAL_SCAN_PARAMS
    horizontal_param = config.HORIZONTAL_SCAN_PARAMS
    mosaic_param     = config.MOSAIC_SCAN_PARAMS
    energy_param     = config.ENERGY_SCAN_PARAMS
    file_param       = config.FILE_SCAN_PARAMS

    cmd_parsers = [
        ('init',           init,              init_param,           "Create configuration file"),
        ('status',         run_status,        mosaic_param,         "Show tomoscan status"),
        ('single',         run_single,        single_param,         "Run a single tomographic scan"),
        ('vertical',       run_vertical,      vertical_param,       "Run a vertical tomographic scan"),
        ('horizontal',     run_horizontal,    horizontal_param,     "Run a horizontal tomographic scan"),
        ('mosaic',         run_mosaic,        mosaic_param,         "Run a mosaic tomographic scan"),
        ('energy',         run_energy,        energy_param,         "Run an energy tomographic scan"),
        ('file',           run_file,          file_param,           "Run a series of scans using the position stored in a configuration file"),
    ]

    subparsers = parser.add_subparsers(title="Commands", metavar='')

    for cmd, func, sections, text in cmd_parsers:
        cmd_params = config.Params(sections=sections)
        cmd_parser = subparsers.add_parser(cmd, help=text, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
        cmd_parser = cmd_params.add_arguments(cmd_parser)
        cmd_parser.set_defaults(_func=func)

    args = config.parse_known_args(parser, subparser=True)
    # args.scan_type is an internal parameters used to log the scan type in the args.config () file
    args.scan_type = ''
    try:
        args._func(args)
    except RuntimeError as e:
        log.error(str(e))
        sys.exit(1)


if __name__ == '__main__':
    main()
