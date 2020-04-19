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
Data Management Lib for Sector 2-BM and 32-ID internal data transfer.
"""

from __future__ import print_function

import os
import subprocess
import pathlib
from paramiko import SSHClient

from tomoscan import log


def check_remote_directory(remote_server, remote_dir):
    try:
        rcmd = 'ls ' + remote_dir
        # rcmd is the command used to check if the remote directory exists
        subprocess.check_call(['ssh', remote_server, rcmd], stderr=open(os.devnull, 'wb'), stdout=open(os.devnull, 'wb'))
        log.warning('      *** remote directory %s exists' % (remote_dir))
        return 0

    except subprocess.CalledProcessError as e: 
        # log.info('      *** return code = %d' % (e.returncode))
        log.warning('      *** remote directory %s does not exist' % (remote_dir))
        if e.returncode == 2:
            return e.returncode
        else:
            log.error('  *** Unknown error code returned: %d' % (e.returncode))
            return -1


def create_remote_directory(remote_server, remote_dir):
    cmd = 'mkdir -p ' + remote_dir
    try:
        # log.info('      *** sending command %s' % (cmd))
        log.info('      *** creating remote directory %s' % (remote_dir))
        subprocess.check_call(['ssh', remote_server, cmd])
        log.info('      *** creating remote directory %s: Done!' % (remote_dir))
        return 0

    except subprocess.CalledProcessError as e:
        log.error('  *** Error while creating remote directory. Error code: %d' % (e.returncode))
        return -1


def scp(global_PVs, params):

    log.info(' ')
    log.info('  *** Data transfer')

    remote_server = params.remote_analysis_dir.split(':')[0]
    remote_top_dir = params.remote_analysis_dir.split(':')[1]
    log.info('      *** remote server: %s' % remote_server)
    log.info('      *** remote top directory: %s' % remote_top_dir)

    fname_origin = global_PVs['HDF1_FullFileName_RBV'].get(as_string=True)
    p = pathlib.Path(fname_origin)
    fname_destination = params.remote_analysis_dir + p.parts[-3] + '/' + p.parts[-2] + '/'
    remote_dir = remote_top_dir + p.parts[-3] + '/' + p.parts[-2] + '/'

    log.info('      *** origin: %s' % fname_origin)
    log.info('      *** destination: %s' % fname_destination)
    # log.info('      *** remote directory: %s' % remote_dir)

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


def mkdir(remote_server, remote_dir):

    log.info('Creating directory on server %s:%s' % (remote_server, remote_dir))
    ret = dm_lib.check_remote_directory(remote_server , remote_dir)
    if ret == 2:
        iret = dm_lib.create_remote_directory(remote_server, remote_dir)

