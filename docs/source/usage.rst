=====
Usage
=====


The following 3 Python commands are all that is required to collect a tomography dataset::

>>> from tomoscan_13bm import tomoscan_13bm

This line imports the code for class tomoscan_13bm.  tomoscan_13bm is a class that derives from tomoscan.  
It implements the logic used for scanning at 13-BM-D, but does not hard-code any EPICS PVs
for that specific beamline.  

Currently at 13-BM-D the rotation stage is a stepper motor driven by an OMS-58 motor controller.  
The step pulses from the motor controller are sent to an SIS3820 multi-channel scaler (MCS). 
The MCS is using in external trigger mode to divide the pulse frequency by N, 
where N is the number of stepper-motor pulses per rotation step.
The speed of the rotation motor is set such that the exposure and readout will have just completed
for image N when the trigger  for image N+1 arrives.
The MCS is also used to collect the dark-fields and the flat-fields, using its internal trigger mode and a
dwell time that is equal to the exposure time plus the readout time.

::

>>> ts = tomoscan_13bm("exampleFiles/13bm/TomoCollect_settings.req", {"$(P)":"13BMDPG1:", "$(R)":"TC:"})

This line creates the tomoscan_13bm object.  It takes two arguments that are passed to the 
tomoscan constructor:

- The first argument is the path to the TomoCollect_settings.req autosave request file for the 
  TomoCollect database described below.
- The second argument is a dictionary of macro substitution values for that database file.
  These define the PV prefixes to use when parsing that file.

When the TomoCollect_settings.req file is read it is used to construct all of the EPICS PV names that are used
by tomoscan.  This allows tomoscan to avoid having any hard-coded PV names, and makes it easy to port to a new beamline.

::

>>> ts.flyScan()

This line runs the tomoscan.flyScan() function.  The base class implementation of flyScan does the common operations
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
