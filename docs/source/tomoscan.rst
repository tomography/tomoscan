tomoscan
========

:author: Mark Rivers (University of Chicago)

.. _2bm-tomo: https://github.com/xray-imaging/2bm-tomo


Table of Contents
-----------------

.. contents:: Contents

Introduction
------------

tomoscan is a Python class for collecting computed tomography data
at the APS. tomoscan.py implements a base class with the code that
should be beamline-independent.  Beamline-dependent code is implemented
in classes that inherit from tomoscan.

Advantages compared to current APS tomography Python software
-------------------------------------------------------------

The following describe some of the advantages of ``tomoscan`` compared to the existing 
APS tomography Python software (e.g. `2bm-tomo`_).

- tomoscan is object-oriented with a base class that implements things that
  can be beamline-independent, and derived classes to implement the beamline-specific
  code.

  - The existing software is procedural, rather than object-oriented.  This means that it
    must pass information to each function (e.g. ``global_PVs``, ``params``).
    More importantly it cannot take advantage of inheritance to allow overriding
    functions in a transparent manner.

- tomoscan does not contain any PV prefixes in the Python code.  It reads the prefixes
  from a configuration file, which makes porting to a new beamline very easy.
  The configuration file itself does not even need to be created, it will already exist
  as the EPICS autosave request file for the tomography database.

  - The existing software hard-codes the PV prefixes in the Python code. This
    requires many changes in the code when porting to a new beamline.

- tomoscan will implement a **server mode**.  tomoscan itself only implements the code
  to collect a single tomography dataset, including dark-fields, flat-fields, and projections.
  The server mode will listen for EPICS PVs that command tomoscan to collect a new dataset.
  There will be a status PV that indicates the scan status, indicating when the scan is complete.
  Thus, any EPICS client can be used to create complex scans, and this code does not need to be
  in the same Python process that is running tomoscan.  Possible clients include Python, IDL,
  the EPICS sscan record, SPEC, etc.

  - The existing software requires that scans be run from within the same Python process that is running
    the tomography scan.

- tomoscan is very compact code.  The existing code is less than 400 lines, including the base
  tomoscan class (274 lines) and the derived class for 13-BM (124 lines).  This code collects
  a complete tomography dataset, including dark-fields, flat-fields, projections, and saving a configuration
  file in JSON format at the end of the scan.  The configuration file can be read back in to repeat the same
  scan at a future time.

Usage
-----
 
 The following 3 Python commands are all that is require to collect a tomography dataset:

  >>> from tomoscan_13bm import tomoscan_13bm
  >>> ts = tomoscan_13bm("exampleFiles/13bm/TomoCollect_settings.req", {"$(P)":"13BMDPG1:", "$(R)":"TC:"})
  >>> ts.flyScan()

 The first line above imports the code for class tomoscan_13bm.  tomoscan_13bm is a class that derives
 from tomoscan.  It implements the logic used for scanning at 13-BM-D, but does not hard-code any EPICS PVs
 for that specific beamline.  Currently at 13-BM-D the rotation stage is a stepper motor driven by 
 an OMS-58 motor controller.  The step pulses from the motor controller are sent to an SIS3820 multi-channel
 scaler (MCS). The MCS is using in external trigger mode to divide the pulse frequency by N, 
 where N is the number of stepper-motor pulses per rotation step. The speed of the rotation motor is
 set such that the exposure and readout will have just completed for image N when the trigger 
 for image N+1 arrives.
 The MCS is also used to collect the dark-fields and the flat-fields, using its internal trigger mode and a
 dwell time that is equal to the exposure time plus the readout time.
 
 The second line above creates the tomoscan_13bm object.  It takes two arguments that are passed to the 
 tomoscan constructor:
 - The first argument is the path to the TomoCollect_settings.req autosave request file for the TomoCollect database described below.
 - The second argument is a dictionary of macro substitution values for that database file.  These define
   the PV prefixes to use when parsing that file.

When the TomoCollect_settings.req file is read it is used to construct all of the EPICS PV names that are used
by tomoscan.  This allows tomoscan to avoid having any hard-coded PV names, and makes it easy to port to a new beamline.

The third line above runs the tomoscan.flyScan() function.  The base class implementation of flyScan does the common operations
required for a tomography dataset:
- Calls the beginScan() method in the derived class.  This performs whatever operations are required before the scan.
- Closes the shutter and collects the dark fields by calling the collectDarkFields() method in the derived class. 
  This can be done before the scan, after the scan, both before and after, or never.
- Opens the shutter, moves the sample out, and collects the flat fields by calling the collectFlatFields() method in the derived class. 
  This can be done before the scan, after the scan, both before and after, or never.
- Moves the sample in and calls the collectProjections() method in the derived class.  
  This method waits for the data collection to complete.
- Calls the endScan() method in the derived class to do any post-scan operations required.
  These may include moving the rotation stage back to the start position, putting the camera in Continuous mode, etc.


Simulation driver specific parameters
-------------------------------------


Screenshots
------------

simDetector.adl
~~~~~~~~~~~~~~~

The following is the MEDM screen simDetector.adl for the simulation
detector.
