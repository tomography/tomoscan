
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
import threading
import time
from pathlib import Path

from tomoscan import log


def _ssh_env():
    """Return os.environ without LD_LIBRARY_PATH so conda's OpenSSL does not
    shadow the system libcrypto that the system ssh binary was built against."""
    env = os.environ.copy()
    env.pop('LD_LIBRARY_PATH', None)
    return env


def scp(fname_origin, remote_analysis_dir, local_top_dir=None):

    log.info(' ')
    log.info('  *** Data transfer')

    remote_server = remote_analysis_dir.split(':')[0]
    remote_top_dir = Path(remote_analysis_dir.split(':')[1])
    log.info('      *** remote server: %s' % remote_server)
    log.info('      *** remote top directory: %s' % remote_top_dir)

    p = Path(fname_origin)
    if local_top_dir is not None:
        remote_relative_dir = p.parent.relative_to(local_top_dir)
        remote_dir_path = remote_top_dir / remote_relative_dir
        remote_dir = str(remote_dir_path) + '/'
        fname_destination = remote_server + ':' + remote_dir
    else:
        remote_dir = str(remote_top_dir) + '/' + p.parts[-3] + '/' + p.parts[-2] + '/'
        fname_destination = remote_analysis_dir + p.parts[-3] + '/' + p.parts[-2] + '/'

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
    elif ret != 0:
        log.error('  *** Cannot verify remote directory (SSH error). Exiting')
        return -1
    iret = start_remote_fdt(remote_server)
    if iret != 0:
        log.error('  *** Error starting remote FDT server. Exiting')
        return -1
    start_fdt_transfer(remote_server, str(remote_dir), str(local_fname))
    log.info('  *** Data transfer: Done!')
    return 0


def check_remote_directory(remote_server, remote_dir):
    rcmd = 'ls ' + remote_dir
    result = subprocess.run(['ssh', remote_server, rcmd], stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, env=_ssh_env())
    if result.returncode == 0:
        log.warning('      *** remote directory %s exists' % (remote_dir))
        return 0
    elif result.returncode == 2:
        log.warning('      *** remote directory %s does not exist' % (remote_dir))
        return 2
    else:
        ssh_err = result.stderr.decode(errors='replace').strip()
        log.error('  *** SSH error checking remote directory (code %d): %s' % (result.returncode, ssh_err))
        return -1

def create_remote_directory(remote_server, remote_dir):
    cmd = 'mkdir -p ' + remote_dir
    try:
        log.info('      *** creating remote directory %s' % (remote_dir))
        subprocess.check_call(['ssh', remote_server, cmd], stdin=subprocess.DEVNULL, env=_ssh_env())
        log.info('      *** creating remote directory %s: Done!' % (remote_dir))
        return 0

    except subprocess.CalledProcessError as e:
        log.error('  *** Error while creating remote directory. Error code: %d' % (e.returncode))
        return -1


def start_remote_fdt(remote_server):
    cmd_start_server = "bash -c 'java -jar /APSshare/bin/fdt.jar -S >/dev/null 2>&1'"
    cmd_kill_server = 'lsof -t -i:54321 | xargs -r kill -9'
    try:
        log.info('kill everything working with port 54321 on the server')
        log.info(f'ssh -f {remote_server} {cmd_kill_server}')
        subprocess.check_call(['ssh', '-f', remote_server, cmd_kill_server], stdin=subprocess.DEVNULL, env=_ssh_env())
        time.sleep(1)
        log.info(f'      *** starting fdt server on {remote_server}')
        log.info(f'ssh -f {remote_server} {cmd_start_server}')
        subprocess.check_call(['ssh', '-f', remote_server, cmd_start_server], stdin=subprocess.DEVNULL, env=_ssh_env())
        log.info(f'      *** starting fdt server on {remote_server}: Done!')
        time.sleep(5)
        return 0
    except subprocess.CalledProcessError as e:
        log.error('  *** Error while starting remote fdt server. Error code: %d' % (e.returncode))
        return -1
    

def start_fdt_transfer(remote_server, remote_dir, local_fname):

    remote_server = remote_server.split('@')[-1]
    log_file = f'/tmp/fdt_{int(time.time())}.log'
    cmd = f'java -jar /APSshare/bin/fdt.jar -c {remote_server} -d {remote_dir} {local_fname}'
    log.info(f'      *** starting fdt transfer to {remote_server} (log: {log_file})')

    def _run():
        _REPORT = ('Net Out:', 'Net In:', 'TotalBytes:', 'Transfer period:',
                   'Exit Status:', 'SEVERE', 'WARNING', 'finished with error')
        try:
            with open(log_file, 'w') as lf, open(log_file, 'r') as lr:
                proc = subprocess.Popen(cmd, shell=True, stdout=lf, stderr=subprocess.STDOUT)
                while proc.poll() is None:
                    line = lr.readline()
                    if line:
                        if any(k in line for k in _REPORT):
                            log.info('FDT: ' + line.rstrip())
                    else:
                        time.sleep(0.2)
                # drain remaining output
                for line in lr:
                    if any(k in line for k in _REPORT):
                        log.info('FDT: ' + line.rstrip())
            rc = proc.returncode
            if rc == 0:
                log.info(f'      *** fdt transfer to {remote_server}: Done!')
            else:
                log.error(f'      *** fdt transfer to {remote_server}: FAILED (rc={rc})')
        except Exception as e:
            log.error(f'      *** fdt transfer thread error: {e}')

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return 0
    

