==================
Install directions
==================

Build EPICS base
----------------

.. warning:: Make sure the disk partition hosting ~/epics is not larger than 2 TB. See `tech talk <https://epics.anl.gov/tech-talk/2017/msg00046.php>`_ and  `Diamond Data Storage <https://epics.anl.gov/meetings/2012-10/program/1023-A3_Diamond_Data_Storage.pdf>`_ document.

::

    $ mkdir ~/epics-ts
    $ cd epics-ts
    

- Download EPICS base latest release, i.e. 7.0.3.1., from https://github.com/epics-base/epics-base::

    $ git clone https://github.com/epics-base/epics-base.git
    $ cd epics-base
    $ git submodule init
    $ git submodule update
    $ make distclean (do this in case there was an OS update)
    $ make -sj
    
.. warning:: if you get a *configure/os/CONFIG.rhel9-x86_64.Common: No such file or directory* error issue this in your csh termimal: $ **setenv EPICS_HOST_ARCH linux-x86_64**

Build a minimal synApps
-----------------------

To build a minimal synApp::

    $ cd ~/epics-ts

- Download in ~/epics-ts `assemble_synApps <https://github.com/EPICS-synApps/assemble_synApps/blob/18fff37055bb78bc40a87d3818777adda83c69f9/assemble_synApps>`_.sh
- Edit the assemble_synApps.sh script to include only::
    
    $modules{'ASYN'} = 'R4-44-2';
    $modules{'AUTOSAVE'} = 'R5-11';
    $modules{'BUSY'} = 'R1-7-4';

You can comment out all of the other modules (ALLENBRADLEY, ALIVE, etc.)

- Run::

    $ cd ~/epics-ts
    $ ./assemble_synApps.sh --dir=synApps --base=/home/beams/FAST/epics-ts/epics-base

- This will create a synApps/support directory::

    $ cd synApps/support/

- Clone the tomoscan module into synApps/support::
    
    $ git clone https://github.com/tomography/tomoscan.git

.. warning:: If you are a tomoScan developer you should clone your fork.

- Edit configure/RELEASE add this line to the end::
    
    TOMOSCAN=$(SUPPORT)/tomoscan

- Verify that synApps/support/tomoscan/configure/RELEASE::

    EPICS_BASE=/home/beams/FAST/epics-ts/epics-base
    SUPPORT=/home/beams/FAST/epics-ts/synApps/support

are set to the correct EPICS_BASE and SUPPORT directories and that::

    BUSY
    AUTOSAVE
    ASYN

point to the version installed.

- Run the following commands::

    $ cd ~/epics-ts/synApps/support/
    $ make release
    $ make -sj

Testing the installation
------------------------

- Start the epics ioc and associated medm screen with::

    $ cd ~/epics-ts/synApps/support/tomoscan/iocBoot/iocTomoScan_13BM_PSO
    $ start_IOC
    $ start_medm


Python server
-------------

- create a dedicated conda environment::

    $ conda create --name tomoscan python=3.9
    $ conda activate tomoscan

and install all packages listed in the `requirements <https://github.com/tomoscan/tomoscan/blob/master/envs/requirements.txt>`_.txt file then

::

    $ cd ~/epics-ts/synApps/support/tomoscan
    $ pip install .
    $ cd ~/epics-ts/synApps/support/tomoscan/iocBoot/iocTomoScan_13BM_PSO/
    $ python -i start_tomoscan.py


Beamline customization
----------------------

tomoScan
~~~~~~~~

Below are the customization steps for 2-BM, you can use these as templates for your beamline.

- Create in ~/epics-ts/synApps/support/tomoscan/tomoScanApp/Db
    - tomoScan_2BM_settings.req
    - tomoScan_2BM.template

- Create in ~/epics-ts/synApps/support/tomoscan/tomoScanApp/op/adl
    - tomoScan_2BM.adl

add here custom PVs required to run tomography at your beamline.

::

    $ mkdir ~/epics-ts/synApps/support/tomoscan/iocBoot/iocTomoScan_2BM
    $ cd ~/epics-ts/synApps/support/tomoscan/iocBoot/
    $ cp -r iocTomoScan_13BM/* iocTomoScan_2BM/

::

    $ cd ~/epics-ts/synApps/support/tomoscan/iocBoot/

- Edit iocBoot/iocTomoScan_2BM/auto_settings.req
    - file "tomoScan_settings.req", P=$(P), R=$(R)
    - file "tomoScan_2BM_settings.req", P=$(P), R=$(R)

- Edit iocBoot/iocTomoScan_2BM/st.cmd to match the name you want to assign to the TomoScan ioc
    - epicsEnvSet("P", "2bma:")
    - epicsEnvSet("R", "TomoScan:")

- Edit iocBoot/iocTomoScan_2BM/start_medm to match the name assigned to the TomoScan ioc
    -  medm -x -macro "P=2bma:,R=TomoScan:,BEAMLINE=tomoScan_2BM" ../../tomoScanApp/op/adl/tomoScan.adl &

- Edit iocBoot/iocTomoScan_2BM/start_tomoscan_2bm.py
    - from tomoscan.tomoscan_2bm import TomoScan2BM
    - ts = TomoScan2BM(["../../db/tomoScan_settings.req","../../db/tomoScan_2BM_settings.req"], {"$(P)":"2bma:", "$(R)":"TomoScan:"})


- Edit iocBoot/iocTomoScan_2BM/tomoScan.substitutions
    - to match the custom PVs required to run tomography at your beamline.

::
    
    file "$(TOP)/db/tomoScan.template"
    {
    pattern
    {  P,      R,      CAMERA,    FILE_PLUGIN,   ROTATION,  SAMPLE_X,  SAMPLE_Y,      CLOSE_SHUTTER,        CLOSE_VALUE,        OPEN_SHUTTER,         OPEN_VALUE}
    {2bma:, TomoScan:, 2bmbSP1:, 2bmbSP1:HDF1:,  2bma:m82,   2bma:m49,  2bma:m20,  2bma:A_shutter:close.VAL,    1,        2bma:A_shutter:open.VAL,      1}
    }

    # For the Ensemble PSO_ENC_PER_ROTATION is a signed number containing the number of encoder pulses per rotation in positive dial coordinates
    file "$(TOP)/db/tomoScan_PSO.template"
    {
    pattern
    {  P,       R,     PSO_MODEL, PSO_PORT, PSO_AXIS_NAME, PSO_ENC_INPUT, PSO_ENC_PER_ROTATION}
    {2bma:, TomoScan:,    0,      PSO_PORT,      X,             3,            11840158.}
    }

    file "$(TOP)/db/tomoScan_2BM.template"
    {
    pattern
    {  P,      R,           BEAM_READY,     READY_VALUE,    CLOSE_FAST_SHUTTER,  CLOSE_FAST_VALUE,   OPEN_FAST_SHUTTER,  OPEN_FAST_VALUE,         SHUTTER_STATUS,}
    {2bma:, TomoScan:, ACIS:ShutterPermit,       1,             2bma:m23,               0,                 2bma:m23,              1,           PA:02BM:STA_A_FES_OPEN_PL,}
    }

then::

    $ cd ~/epics-ts/synApps/support
    $ make release
    $ make -sj

Python class
~~~~~~~~~~~~

- Create in ~/epics-ts/synApps/support/tomoscan/tomoscan/
    - tomoscan_2bm.py

to implemented a derived classes that inherit from ~/epics-ts/synApps/support/tomoscan/tomoscan/tomoscan.py
This derived class will handle any beamline specific hardware (fast shutter, fly scan hardware etc.)

To install the python class as a libray::

    $ cd ~/epics-ts/synApps/support/tomoscan/
    $ conda activate tomoscan
    $ pip install .

