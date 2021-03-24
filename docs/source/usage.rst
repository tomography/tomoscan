=====
Usage
=====


The following Python commands are all that is required to collect a tomography dataset::

>>> from tomoscan_13bm_pso import TomoScan13BM_PSO

This line imports the code for class TomoScan13BM_PSO.  TomoScan13BM_PSO is a class that derives from TomoScan_PSO,
which in turn derives from TomoScan.  
It implements the logic used for scanning at 13-BM-D, but does not hard-code any EPICS PVs
for that specific beamline.  

The rotation stage is an air-bearing rotation stage driven by an Aerotech NDrive controller.
The NDrive is programmed to output PSO trigger pulses at fixed angular increments of the rotation stage.  
The speed of the rotation motor is set such that the exposure and readout will have just completed
for image N when the trigger  for image N+1 arrives.

::

  ts = TomoScan13BM_PSO(["../../db/tomoScan_settings.req",
                         "../../db/tomoScan_PSO_settings.req",
                         "../../db/tomoScan_13BM_settings.req"],
                        {"$(P)":"13BMDPG1:", "$(R)":"TS:"})

This line creates the TomoScan13BM_PSO object.  It takes two arguments that are passed to the 
TomoScan constructor:

- The first argument is a list of paths to the autosave request files for the databases.
  These are described in the :doc:`tomoScanApp` documentation.
- The second argument is a dictionary of macro substitution values for those request files.
  These define the PV prefixes to use when parsing the files.

After creating the TomoScan13BM object in the line shown above it is ready to perform scans that are 
initiated by the $(P)$(R)StartScan PV from any Channel Access client.

The following two commands will run scans from the Python prompt.

::

>>> ts.fly_scan()

The above line runs the TomoScan.fly_scan() function in the Python main thread.  This means that the Python command
line will not be available until the scan completes.  The scan can be aborted by typing ^C.

>>> ts.run_fly_scan()

The above line runs the ``TomoScan.fly_scan()`` function in a new Python thread.  This means that the Python command
line is available immediately.  The scan can be aborted by typing ^C or by typing the command ``ts.abort_scan()``.

The base class implementation of ``fly_scan()`` does the common operations required for a tomography dataset:

- Calls the ``begin_scan()`` method to perform whatever operations are required before the scan. 
- Calls the ``collect_dark_fields()`` method to collect the dark fields.  
  This can be done before the scan, after the scan, both before and after, or never.
- Calls the ``collect_flat_fields()`` method to collect the flat fields. 
  This can be done before the scan, after the scan, both before and after, or never.
- Calls the ``collect_projections()`` method to collect all of the projections.
  This method waits for the data collection to complete.
- Calls the ``end_scan()`` method to do any post-scan operations required.
  These may include moving the rotation stage back to the start position, putting the camera in Continuous mode, etc.
  
``begin_scan()``, ``collect_dark_fields()``, ``collect_flat_fields()``, ``collect_projections()``, and ``end_scan()``
all have implementations in the base class, but will commonly also be implemented in the derived class.
The derived class will normally call the base class to perform the operations that are not beamline-specific. 

tomoscan-cli
------------

Installing tomoscan as a python libray with::

    $ cd ~/epics/synApps/support/tomoscan/
    $ python setup.py install

enables the tomoscan commnand line interface. To use it::

    $ tomoscan -h
    usage: tomoscan [-h] [--config FILE] [--version]  ...
    optional arguments:
      -h, --help     show this help message and exit
      --config FILE  File name of configuration file
      --version      show program's version number and exit

      Commands:
  
    init         Create configuration file
    status       Show tomoscan status
    single       Run a single tomographic scan
    vertical     Run a vertical tomographic scan
    horizontal   Run a horizontal tomographic scan
    mosaic       Run a mosaic tomographic scan

each command help is accessible with ``-h``::

  Usage: tomoscan vertical [-h] [--scan-type SCAN_TYPE]
                         [--tomoscan-db-home FILE]
                         [--tomoscan-prefix TOMOSCAN_PREFIX]
                         [--in-situ-pv IN_SITU_PV]
                         [--in-situ-pv-rbv IN_SITU_PV_RBV]
                         [--in-situ-start IN_SITU_START]
                         [--in-situ-step-size IN_SITU_STEP_SIZE]
                         [--sleep-steps SLEEP_STEPS] [--sleep-time SLEEP_TIME]
                         [--vertical-start VERTICAL_START]
                         [--vertical-step-size VERTICAL_STEP_SIZE]
                         [--vertical-steps VERTICAL_STEPS] [--config FILE]
                         [--in-situ] [--logs-home FILE] [--sleep] [--testing]
                         [--verbose]

  optional arguments:
  -h, --help            show this help message and exit
  --scan-type SCAN_TYPE
                        For internal use to log the tomoscan status (default: )
  --tomoscan-db-home FILE
                        Log file directory 
                        (default: /home/user2bmb/epics/synApps/support/tomoscan/db/)
  --tomoscan-prefix TOMOSCAN_PREFIX
                        The tomoscan prefix, i.e.'13BMDPG1:TS:' or
                        '2bma:TomoScan:' (default: 2bma:TomoScan:)
  --in-situ-pv IN_SITU_PV
                        Name of the in-situ EPICS process variable to set
                        (default: )
  --in-situ-pv-rbv IN_SITU_PV_RBV
                        Name of the in-situ EPICS process variable to read back (default: )
  --in-situ-start IN_SITU_START
                        In-situ start (default: 0)
  --in-situ-step-size IN_SITU_STEP_SIZE
                        In-situ step size (default: 1)
  --sleep-steps SLEEP_STEPS
                        Number of sleep/in-situ steps (default: 1)
  --sleep-time SLEEP_TIME
                        Wait time (s) between each data collection scan (default: 0)
  --vertical-start VERTICAL_START
                        Vertical start position (mm) (default: 0)
  --vertical-step-size VERTICAL_STEP_SIZE
                        Vertical step size (mm) (default: 1)
  --vertical-steps VERTICAL_STEPS
                        Number of vertical steps (default: 1)
  --config FILE         File name of configuration file 
                        (default: /home/user2bmb/tomoscan.conf)
  --in-situ             Enable in-situ PV scan during sleep time (default: False)
  --logs-home FILE      Log file directory (default: /home/user2bmb/logs)
  --sleep               Enable sleep time between tomography scans (default: False)
  --testing             Enable test mode, tomography scan will not run (default: False)
  --verbose             Verbose output (default: False)
