
"""
Data Management module to support data transfer from data collection to data analysis computer

To use at your beamline:

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
from pathlib import Path
import time

from tomoscan import log


def scp(fname_origin, remote_analysis_dir):

    log.info(' ')
    log.info('  *** Data transfer')

    remote_server = remote_analysis_dir.split(':')[0]
    remote_top_dir = remote_analysis_dir.split(':')[1]
    log.info('      *** remote server: %s' % remote_server)
    log.info('      *** remote top directory: %s' % remote_top_dir)

    p = Path(fname_origin)
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


def fdt_scp(local_fname, remote_analysis_dir, local_top_dir):

    log.info(' ')
    log.info('  *** Data transfer')

    remote_server = remote_analysis_dir.split(':')[0]
    remote_top_dir = Path(remote_analysis_dir.split(':')[1])

    #Remote directory is same as local file directory, relative to local_top_dir
    local_file_path = Path(local_fname)
    remote_relative_dir = local_file_path.parent.relative_to(local_top_dir)
    remote_dir = remote_top_dir.joinpath(remote_relative_dir)
    log.info(f'      *** remote server: {remote_server}')
    log.info(f'      *** remote top directory: {str(remote_top_dir)}')

    log.info('      *** origin: %s' % local_fname)
    log.info('      *** destination: %s' % remote_dir)

    ret = check_remote_directory(remote_server, str(remote_dir))

    if ret == 2:
        iret = create_remote_directory(remote_server, str(remote_dir))
        if iret != 0:
            log.error('  *** Error making a remote directory.  Exiting')
            return -1
    start_remote_fdt(remote_server)
    start_fdt_transfer(remote_server, str(remote_dir), str(local_fname))
    log.info('  *** Data transfer: Done!')
    return 0


def check_remote_directory(remote_server, remote_dir):
    try:
        rcmd = 'ls ' + remote_dir
        # rcmd is the command used to check if the remote directory exists
        subprocess.check_call(['ssh', '-t', remote_server, rcmd], stderr=open(os.devnull, 'wb'), stdout=open(os.devnull, 'wb'))
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
        subprocess.check_call(['ssh', '-t', remote_server, cmd])
        log.info('      *** creating remote directory %s: Done!' % (remote_dir))
        return 0

    except subprocess.CalledProcessError as e:
        log.error('  *** Error while creating remote directory. Error code: %d' % (e.returncode))
        return -1


def start_remote_fdt(remote_server):
    cmd = 'java -jar /APSshare/bin/fdt.jar -S'
    try:
        log.info(f'      *** starting fdt server on {remote_server}')
        log.info('ssh -f {remote_server} {cmd}')
        subprocess.check_call(['ssh', '-f', remote_server, cmd])
        log.info(f'      *** starting fdt server on {remote_server}: Done!')
        time.sleep(5)
        return 0

    except subprocess.CalledProcessError as e:
        log.error('  *** Error while starting remote fdt server. Error code: %d' % (e.returncode))
        return -1
    

def start_fdt_transfer(remote_server, remote_dir, local_fname):
    try:
        log.info(f'      *** starting fdt transfer to {remote_server}')
        log.info(f'java -jar /APSshare/bin/fdt.jar -c {remote_server} -d {remote_dir} {local_fname}')
        os.system(f'java -jar /APSshare/bin/fdt.jar -c {remote_server} -d {remote_dir} {local_fname}')
        log.info(f'      *** starting fdt transfer to {remote_server}: Done!')
        return 0

    except:
        log.error(f'  *** Error during fdt transfer to {remote_server}')
