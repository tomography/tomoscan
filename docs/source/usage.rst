=====
Usage
=====


The following Python commands are all that is required to collect a tomography dataset::

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


>>> ts = tomoscan_13bm("../tomoScanApp/Db/tomoScan_settings.req", {"$(P)":"TSTest:", "$(R)":"TS1:"})

This line creates the tomoscan_13bm object.  It takes two arguments that are passed to the 
tomoscan constructor:

- The first argument is the path to the tomoScan_settings.req autosave request file for the 
  tomoScan database described below.  
- The second argument is a dictionary of macro substitution values for that database file.
  These define the PV prefixes to use when parsing files described above.
  
The tomoScan_settings.req file contains 4 types of PVs:

1) Configuration PVs. These are PVs the control how tomography scans are collected, and provide metadata
   about the scan. An example is $(P)$(R)RotationStart.  These have the following properties:

  - They are saved by autosave in the auto_settings.sav file.
  - They are saved by tomoscan in configuration files. 
  - They do **not** contain the string "PVName" or "PVPrefix" in their PV names.
  - They appear as normal lines in the file, not in comment lines.

2) PVs that contain the name of another PV.  These are used to configure tomoscan to control a particular motor
   for the rotation axis, sample X axis, etc.  An example is $(P)$(R)RotationPVName.  
   These have the following properties:

  - They contain the string "PVName" in their PV names.
  - They are saved by autosave in the auto_settings.sav file.
  - They are **not** saved by tomoscan in configuration files. 
  - They appear as normal lines in the file, not in comment lines.

3) PVs that contain the PV prefix for a set of other PVs.  These are used to configure tomoscan to control a particular 
   areaDetector camera, etc.  Examples are (P)$(R)CameraPVPrefix and $(P)$(R)FilePluginPVPrefix.  
   These have the following properties:

  - They contain the string "PVPrefix" in their PV names.
  - They are saved by autosave in the auto_settings.sav file.
  - They are **not** saved by tomoscan in configuration files. 
  - They appear as normal lines in the file, not in comment lines.

4) PVs that are required by tomoscan, but which should not be saved and restored by autosave, either because
   they are read-only, or because writing to them when the IOC starts might have unwanted consequences.
   These have the following properties:

  - They appear in comment lines in the file.  The comment line must start with the string #controlPV followed by the PV name.
  - They do **not** contain the string "PVName" or "PVPrefix" in their PV names.
  - They are **not** saved by autosave in the auto_settings.sav file.
  - They are **not** saved by tomoscan in configuration files. 

When the tomoScan_settings.req file is read it is used to construct all of the EPICS PV names that are used by tomoscan.
This allows tomoscan to avoid having any hard-coded PV names, and makes it easy to port to a new beamline.

After creating the tomoscan object in the line shown above tomoscan is ready to perform scans that are 
initiated by the $(P)$(R)StartScan PV from any Channel Access client.

The following two commands will run scans from the Python prompt.

::

>>> ts.flyScan()

The above line runs the tomoscan.flyScan() function in the Python main thread.  This means that the Python command
line will not be available until the scan completes.  The scan can be aborted by typing ^C.

>>> ts.runFlyScan()

The above line runs the tomoscan.flyScan() function in a new Python thread.  This means that the Python command
line is available immediately.  The scan can be aborted by typing ^C or by typing the command ``ts.abortScan()``.

The base class implementation of flyScan does the common operations required for a tomography dataset:

- Calls the beginScan() method to perform whatever operations are required before the scan. 
  beginScan has an implementation in the base class, but will commonly also be implemented in the derived class.
  The derived class will normally call the base class to perform the operations that are not beamline-specific. 
- Closes the shutter and collects the dark fields by calling the collectDarkFields() method in the derived class. 
  This can be done before the scan, after the scan, both before and after, or never.
- Opens the shutter, moves the sample out, and collects the flat fields by calling the collectFlatFields() method in the derived class. 
  This can be done before the scan, after the scan, both before and after, or never.
- Moves the sample in and calls the collectProjections() method in the derived class.  
  This method waits for the data collection to complete.
- Calls the endScan() method to do any post-scan operations required.
  These may include moving the rotation stage back to the start position, putting the camera in Continuous mode, etc.
  endScan has an implementation in the base class, but will commonly also be implemented in the derived class.
  The derived class will normally call the base class to perform the operations that are not beamline-specific. 
