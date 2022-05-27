"""
tomoscan config file

This file is used by the command line interface to set, save and  restore the tomoscan 
This file contains all of the PVs used by the tomoscan base class.

Lines that begin with #controlPV are not saved by autosave, but they are used by tomoscan.  
These PVs are not saved in the tomoscan configuration file.

"""

import os
import sys
import shutil
import pathlib
import argparse
import configparser
import h5py
import numpy as np

from collections import OrderedDict

from tomoscan import log
from tomoscan import util
from tomoscan import __version__

home = os.path.expanduser("~")
LOGS_HOME = os.path.join(home, 'logs')
CONFIG_FILE_NAME = os.path.join(home, 'tomoscan.conf')
SCAN_FILE_NAME = os.path.join(home, 'scan.json')

SECTIONS = OrderedDict()

SECTIONS['general'] = {
    'config': {
        'default': CONFIG_FILE_NAME,
        'type': str,
        'help': "File name of configuration file. Default: ~/tomoscan.conf",
        'metavar': 'FILE'},
    'scan-file': {
        'default': SCAN_FILE_NAME,
        'type': str,
        'help': "File name of scan file contaning a dictionary listing multiple scan parameters. Default: ~/scan.json",
        'metavar': 'FILE'},
    'logs-home': {
        'default': LOGS_HOME,
        'type': str,
        'help': "Log file directory",
        'metavar': 'FILE'},
    'logs-home': {
        'default': LOGS_HOME,
        'type': str,
        'help': "Log file directory",
        'metavar': 'FILE'},
    'verbose': {
        'default': False,
        'help': 'Verbose output',
        'action': 'store_true'},
    'sleep': {
        'default': False,
        'help': 'Enable sleep time between tomography scans',
        'action': 'store_true'},
    'in-situ': {
        'default': False,
        'help': 'Enable in-situ PV scan during sleep time',
        'action': 'store_true'},
    'testing': {
        'default': False,
        'help': 'Enable test mode, tomography scan will not run',
        'action': 'store_true'},
        }

SECTIONS['tomoscan'] = {
    'tomoscan-prefix':{
        'default': '2bma:TomoScan:',
        'type': str,
        'help': "The tomoscan prefix, i.e.'13BMDPG1:TS:' or '2bma:TomoScan:' "},
    'scan-type':{
        'default': '',
        'type': str,
        'help': "Scan type",
        'default' : "Single",
        'choices': ['Single','Vertical', 'Horizontal', 'Mosaic', 'Energy', 'File']}, 
        }

SECTIONS['in-situ'] = {
    'in-situ-pv': {
        'default': '',
        'type': str,
        'help': "Name of the in-situ EPICS process variable to set"},
    'in-situ-pv-rbv': {
        'default': '',
        'type': str,
        'help': "Name of the in-situ EPICS process variable to read back"},
    'in-situ-start': {
        'default': 0,
        'type': float,
        'help': "In-situ start"},
    'in-situ-step-size': {
        'default': 1,
        'type': float,
        'help': "In-situ step size"},
    'sleep-time': {
        'default': 0,
        'type': float,
        'help': "Wait time (s) between each data collection scan"},
    'sleep-steps': {
        'type': util.positive_int,
        'default': 1,
        'help': "Number of sleep/in-situ steps"},
       }

SECTIONS['vertical'] = {
    'vertical-start': {
        'default': 0,
        'type': float,
        'help': "Vertical start position (mm)"},
    'vertical-step-size': {
        'default': 1,
        'type': float,
        'help': "Vertical step size (mm)"},
    'vertical-steps': {
        'default': 1,
        'type': util.positive_int,
        'help': "Number of vertical steps"},
    }

SECTIONS['horizontal'] = {
    'horizontal-start': {
        'default': 0,
        'type': float,
        'help': "Horizontal start position (mm)"},
    'horizontal-step-size': {
        'default': 1,
        'type': float,
        'help': "Horizontal step size (mm)"},
    'horizontal-steps': {
        'default': 1,
        'type': util.positive_int,
        'help': "Number of horizontal steps"},
    }

SECTIONS['energy'] = {
    'file-energies': {
        'default': '',
        'type': str,
        'help': "Numpy file with an array of energies in keV"},
    'file-params1': {
        'default': '/home/beams/USERTXM/epics/synApps/support/txmoptics/iocBoot/iocTXMOptics/energy1.txt',
        'type': str,
        'help': "Txt file with PV values corresponding to optics positions for the first energy"},    
    'file-params2': {
        'default': '/home/beams/USERTXM/epics/synApps/support/txmoptics/iocBoot/iocTXMOptics/energy2.txt',
        'type': str,
        'help': "Txt file with PV values corresponding to optics positions for the second energy"},    
    }

SECTIONS['file'] = {
    'num-scans': {
        'default': 10,
        'type': util.positive_int,
        'help': "Horizontal scan position"},
    'sample-x': {
        'default': 0,
        'type': float,
        'help': "Horizontal scan position"},
    'sample-y': {
        'default': 0,
        'type': float,
        'help': "Vertical scan position"},
    }

INIT_PARAMS = ('tomoscan', 'file')
SINGLE_SCAN_PARAMS = ('tomoscan', 'in-situ')
VERTICAL_SCAN_PARAMS = SINGLE_SCAN_PARAMS + ('vertical',)
HORIZONTAL_SCAN_PARAMS = SINGLE_SCAN_PARAMS + ('horizontal',)
MOSAIC_SCAN_PARAMS = SINGLE_SCAN_PARAMS + ('vertical', 'horizontal')
ENERGY_SCAN_PARAMS = SINGLE_SCAN_PARAMS + ('energy',)
FILE_SCAN_PARAMS = SINGLE_SCAN_PARAMS + ('file', )

NICE_NAMES = ('General', 'Tomoscan', 'In-situ Scans', 'Vertical Scan', "Horizonatal Scan", "Energy", "File")

def get_config_name():
    """Get the command line --config option."""
    name = CONFIG_FILE_NAME
    for i, arg in enumerate(sys.argv):
        if arg.startswith('--config'):
            if arg == '--config':
                return sys.argv[i + 1]
            else:
                name = sys.argv[i].split('--config')[1]
                if name[0] == '=':
                    name = name[1:]
                return name

    return name


def parse_known_args(parser, subparser=False):
    """
    Parse arguments from file and then override by the ones specified on the
    command line. Use *parser* for parsing and is *subparser* is True take into
    account that there is a value on the command line specifying the subparser.
    """
    if len(sys.argv) > 1:
        subparser_value = [sys.argv[1]] if subparser else []
        config_values = config_to_list(config_name=get_config_name())
        values = subparser_value + config_values + sys.argv[1:]
    else:
        values = ""

    return parser.parse_known_args(values)[0]


def config_to_list(config_name=CONFIG_FILE_NAME):
    """
    Read arguments from config file and convert them to a list of keys and
    values as sys.argv does when they are specified on the command line.
    *config_name* is the file name of the config file.
    """
    result = []
    config = configparser.ConfigParser()

    if not config.read([config_name]):
        return []

    for section in SECTIONS:
        for name, opts in ((n, o) for n, o in SECTIONS[section].items() if config.has_option(section, n)):
            value = config.get(section, name)

            if value != '' and value != 'None':
                action = opts.get('action', None)

                if action == 'store_true' and value == 'True':
                    # Only the key is on the command line for this action
                    result.append('--{}'.format(name))

                if not action == 'store_true':
                    if opts.get('nargs', None) == '+':
                        result.append('--{}'.format(name))
                        result.extend((v.strip() for v in value.split(',')))
                    else:
                        result.append('--{}={}'.format(name, value))

    return result
   

class Params(object):
    def __init__(self, sections=()):
        self.sections = sections + ('general', )

    def add_parser_args(self, parser):
        for section in self.sections:
            for name in sorted(SECTIONS[section]):
                opts = SECTIONS[section][name]
                parser.add_argument('--{}'.format(name), **opts)

    def add_arguments(self, parser):
        self.add_parser_args(parser)
        return parser

    def get_defaults(self):
        parser = argparse.ArgumentParser()
        self.add_arguments(parser)

        return parser.parse_args('')

def write(config_file, args=None, sections=None):
    """
    Write *config_file* with values from *args* if they are specified,
    otherwise use the defaults. If *sections* are specified, write values from
    *args* only to those sections, use the defaults on the remaining ones.
    """
    config = configparser.ConfigParser()

    for section in SECTIONS:
        config.add_section(section)
        for name, opts in SECTIONS[section].items():
            if args and sections and section in sections and hasattr(args, name.replace('-', '_')):
                value = getattr(args, name.replace('-', '_'))

                if isinstance(value, list):
                    value = ', '.join(value)
            else:
                value = opts['default'] if opts['default'] is not None else ''

            prefix = '# ' if value == '' else ''

            if name != 'config':
                config.set(section, prefix + name, str(value))

    with open(config_file, 'w') as f:
        config.write(f)

def show_config(args):
    """Log all values set in the args namespace.

    Arguments are grouped according to their section and logged alphabetically
    using the DEBUG log level thus --verbose is required.
    """
    args = args.__dict__

    log.warning('tomoscan status start')
    for section, name in zip(SECTIONS, NICE_NAMES):
        entries = sorted((k for k in args.keys() if k.replace('_', '-') in SECTIONS[section]))
        if entries:
            for entry in entries:
                value = args[entry] if args[entry] != None else "-"
                log.info("  {:<16} {}".format(entry, value))

    log.warning('tomoscan status end')
 

