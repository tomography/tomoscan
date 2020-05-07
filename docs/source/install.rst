==================
Install directions
==================


Build a minimal synApps
-----------------------

To build a minimal synApp::

    $ mkdir ~/epics
    $ cd epics


- Download in ~/epics `assemble_synApps <https://github.com/EPICS-synApps/support/blob/master/assemble_synApps.sh>`_.sh
- Edit the assemble_synApps.sh script as follows:
    - Set FULL_CLONE=True
    - Set EPICS_BASE to point to the location of EPICS base.  This could be on APSshare (the default), or a local version you built.
    - For tomoscan you only need BUSY and AUTOSAVE.  You can comment out all of the other modules (ALLENBRADLEY, ALIVE, etc.)

- Run::

    $ assemble_synApps.sh


- This will create a synApps/ directory::

    $ cd synApps/support/

- Edit  ~/epics/synApps/support/busy-R1-7-2/configure/RELEASE
    - comment out the ASYN line.
- Clone the tomoscan module into synApps/support::
    
    $ git clone https://github.com/tomography/tomoscan

- Edit ~/epics/synApps/support/configure/RELEASE
    - add this line to the end:
    - TOMOSCAN=$(SUPPORT)/tomoscan

- Edit ~/epics/synApps/support/Makefile
    - add this line to the end of the MODULE_LIST
    - MODULE_LIST += TOMOSCAN

- Run the following commands::

    $ make release
    $ make -sj

Run TomoScan ioc
----------------

Once synApps is built you can start the epics ioc and associated medm screen with::

    $ cd ~/epics/synApps/support/tomoscan/iocBoot/iocTomoScan
    $ start_IOC
    $ start_medm


Bemaline customization
----------------------


need to customize the following to work on your beamline:

- edit /epics/synApps/support/tomoscan/configure and modify the EPICS_BASE location to match your EPICS installation, for 2-BM this is::

    EPICS_BASE=/APSshare/epics/base-3.15.6

- edit tomoscan/iocBoot/tomoScan.substitutions file to match your PVs for tomoScan.template and beamline specific tomoScan_xxYY.template, for 2-BM this is::
    
    file "$(TOP)/db/tomoScan.template"
    {
    pattern
    {  P,      R,      CAMERA,    FILE_PLUGIN,   ROTATION,  SAMPLE_X,  SAMPLE_Y,      CLOSE_SHUTTER,        CLOSE_VALUE,        OPEN_SHUTTER,         OPEN_VALUE}
    {2bma:, TomoScan:, 2bmbSP1:, 2bmbSP1:HDF1:,  2bma:m82,  2bma:m49,  2bma:m20,  2bma:A_shutter:close.VAL,    1,        2bma:A_shutter:open.VAL,      1}
    }

    file "$(TOP)/db/tomoScan_2BM.template"
    {
    pattern
    {  P,      R,         PSO,           BEAM_READY,      READY_VALUE,    CLOSE_FAST_SHUTTER,  CLOSE_FAST_VALUE,        OPEN_FAST_SHUTTER,         OPEN_FAST_VALUE,}
    {2bma:, TomoScan:, 2bma:PSOFly2:,   ACIS:ShutterPermit,    1,             2bma:m23,                0,                    2bma:m23,                1,}
    }

- edit tomoscan/iocBoot/st.cdm to match your ioc name::

    picsEnvSet("P", "2bma:")
    epicsEnvSet("R", "TomoScan:")

- edit tomoscan/iocBoot/iocTomoScan/auto_settings.req to use your beamline setting.req file::

    file "tomoScan_settings.req", P=$(P), R=$(R)
    file "tomoScan_2BM_settings.req", P=$(P), R=$(R)

then::

    $ cd ~/epics/synApps/support
    $ make release
    $ make -sj


To install the python class as a libray::

    $ cd ~/epics/synApps/support/tomoscan/
    $ python setup.py install

