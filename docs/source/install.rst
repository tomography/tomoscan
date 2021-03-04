==================
Install directions
==================

Build EPICS base
----------------

.. warning:: Make sure the disk partition hosting ~/epics is not larger than 2 TB. See `tech talk <https://epics.anl.gov/tech-talk/2017/msg00046.php>`_ and  `Diamond Data Storage <https://epics.anl.gov/meetings/2012-10/program/1023-A3_Diamond_Data_Storage.pdf>`_ document.

::

    $ mkdir ~/epics
    $ cd epics
    

- Download EPICS base latest release, i.e. 7.0.3.1., from https://github.com/epics-base/epics-base::

    $ git clone https://github.com/epics-base/epics-base.git
    $ cd epics-base
    $ make -sj
    

Build a minimal synApps
-----------------------

To build a minimal synApp::

    $ cd ~/epics

- Download in ~/epics `assemble_synApps <https://github.com/EPICS-synApps/support/blob/master/assemble_synApps.sh>`_.sh
- Edit the assemble_synApps.sh script as follows:
    - Set FULL_CLONE=True
    - Set EPICS_BASE to point to local version just built: ~/epics/epics-base.
    - For tomoscan you only need ASYN, BUSY and AUTOSAVE.  You can comment out all of the other modules (ALLENBRADLEY, ALIVE, etc.)

- Run::

    $ assemble_synApps.sh

- This will create a synApps/support directory::

    $ cd synApps/support/

- Edit asyn-RX-YY/configure/RELEASE to comment out the lines starting with::
    
    IPAC=$(SUPPORT)/
    SNCSEQ=$(SUPPORT)/


.. warning:: If building for RedHat8 uncomment **TIRPC=YES** in asyn-RX-YY/configure/CONFIG_SITE


- Clone the tomoscan module into synApps/support::
    
    $ git clone https://github.com/tomography/tomoscan.git

- Edit configure/RELEASE add this line to the end::
    
    TOMOSCAN=$(SUPPORT)/tomoscan

- Edit Makefile add this line to the end of the MODULE_LIST::
    
    MODULE_LIST += TOMOSCAN

- Run the following commands::

    $ make release
    $ make -sj

Testing the installation
------------------------

- Edit /epics/synApps/support/tomoscan/configure
    - Set EPICS_BASE to point to the location of EPICS base:
    - EPICS_BASE=/APSshare/epics/base-3.15.6

- Start the epics ioc and associated medm screen with::

    $ cd ~/epics/synApps/support/tomoscan/iocBoot/iocTomoScan_13BM_PSO
    $ start_IOC
    $ start_medm

Beamline customization
----------------------

tomoScan
~~~~~~~~

Below are the customization steps for 2-BM, you can use these as templates for your beamline.

- Create in ~/epics/synApps/support/tomoscan/tomoScanApp/Db
    - tomoScan_2BM_settings.req
    - tomoScan_2BM.template

- Create in ~/epics/synApps/support/tomoscan/tomoScanApp/op/adl
    - tomoScan_2BM.adl

add here custom PVs required to run tomography at your beamline.

::

    $ mkdir ~/epics/synApps/support/tomoscan/iocBoot/iocTomoScan_2BM
    $ cd ~/epics/synApps/support/tomoscan/iocBoot/
    $ cp -r iocTomoScan_13BM/* iocTomoScan_2BM/

::

    $ cd ~/epics/synApps/support/tomoscan/iocBoot/

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

    $ cd ~/epics/synApps/support
    $ make release
    $ make -sj

Python class
~~~~~~~~~~~~

- Create in ~/epics/synApps/support/tomoscan/tomoscan/
    - tomoscan_2bm.py

to implemented a derived classes that inherit from ~/epics/synApps/support/tomoscan/tomoscan/tomoscan.py
This derived class will handle any beamline specific hardware (fast shutter, fly scan hardware etc.)

To install the python class as a libray::

    $ cd ~/epics/synApps/support/tomoscan/
    $ python setup.py install

