
"""
Data Management module to support data transfer from data collection to data analysis computer

To use in your beamline:

from tomoscan import data_management as dm

def end_scan(self):

    ...

    full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
    remote_analysis_dir = self.epics_pvs['RemoteAnalysisDir'].get(as_string=True)
    dm.scp(full_file_name, remote_analysis_dir)

with remote_analysis_dir formatted as tomo@handyn:/local/data/

"""

import os
import subprocess
import pathlib
from paramiko import SSHClient

from tomoscan import log



def scp(fname_origin, remote_analysis_dir):

    log.info(' ')
    log.info('  *** Data transfer')

    remote_server = remote_analysis_dir.split(':')[0]
    remote_top_dir = remote_analysis_dir.split(':')[1]
    log.info('      *** remote server: %s' % remote_server)
    log.info('      *** remote top directory: %s' % remote_top_dir)

    p = pathlib.Path(fname_origin)
    fname_destination = remote_analysis_dir + p.parts[-3] + '/' + p.parts[-2] + '/'
    remote_dir = remote_top_dir + p.parts[-3] + '/' + p.parts[-2] + '/'

    log.info('      *** origin: %s' % fname_origin)
    log.info('      *** destination: %s' % fname_destination)

    ret = check_remote_directory(remote_server, remote_dir)

    if ret == 0:
        os.system('scp -q ' + fname_origin + ' ' + fname_destination + '&')
        log.info('  *** Data transfer: Done!')
        return 0
    elif ret == 2:
        iret = create_remote_directory(remote_server, remote_dir)
        if iret == 0: 
            os.system('scp -q ' + fname_origin + ' ' + fname_destination + '&')
        log.info('  *** Data transfer: Done!')
        return 0
    else:
        log.error('  *** Quitting the copy operation')
        return -1

def check_remote_directory(remote_server, remote_dir):
    try:
        rcmd = 'ls ' + remote_dir
        # rcmd is the command used to check if the remote directory exists
        subprocess.check_call(['ssh', remote_server, rcmd], stderr=open(os.devnull, 'wb'), stdout=open(os.devnull, 'wb'))
        log.warning('      *** remote directory %s exists' % (remote_dir))
        return 0

    except subprocess.CalledProcessError as e: 
        log.warning('      *** remote directory %s does not exist' % (remote_dir))
        if e.returncode == 2:
            return e.returncode
        else:
            log.error('  *** Unknown error code returned: %d' % (e.returncode))
            return -1

def create_remote_directory(remote_server, remote_dir):
    cmd = 'mkdir -p ' + remote_dir
    try:
        log.info('      *** creating remote directory %s' % (remote_dir))
        subprocess.check_call(['ssh', remote_server, cmd])
        log.info('      *** creating remote directory %s: Done!' % (remote_dir))
        return 0

    except subprocess.CalledProcessError as e:
        log.error('  *** Error while creating remote directory. Error code: %d' % (e.returncode))
        return -1