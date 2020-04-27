=====
Usage
=====


The following Python commands are all that is required to collect a tomography dataset::

>>> from tomoscan_13bm import TomoScan13BM

This line imports the code for class TomoScan13BM.  TomoScan13BM is a class that derives from TomoScan.  
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

>>> ts = TomoScan13BM(["../db/tomoScan_settings.req","../db/tomoScan_13BM_settings.req"], {"$(P)":"TSTest:", "$(R)":"TS1:"})

This line creates the TomoScan13BM object.  It takes two arguments that are passed to the 
TomoScan constructor:

- The first argument is a list of paths to the autosave request files for the databases described below.  
- The second argument is a dictionary of macro substitution values for those request files.
  These define the PV prefixes to use when parsing the files.
  
The tomoScan_settings.req and tomoScan_13BM_settings.req files contains 4 types of PVs:

1) Configuration PVs. These are PVs the control how tomography scans are collected, and provide metadata
   about the scan. An example is $(P)$(R)RotationStart.  These have the following properties:

  - They are saved by autosave in the auto_settings.sav file.
  - They are saved by TomoScan in configuration files. 
  - They do **not** contain the string "PVName" or "PVPrefix" in their PV names.
  - They appear as normal lines in the file, not in comment lines.

2) PVs that contain the name of another PV.  These are used to configure TomoScan to control a particular motor
   for the rotation axis, sample X axis, etc.  An example is $(P)$(R)RotationPVName.  
   These have the following properties:

  - They contain the string "PVName" in their PV names.
  - They are saved by autosave in the auto_settings.sav file.
  - They are **not** saved by TomoScan in configuration files. 
  - They appear as normal lines in the file, not in comment lines.

3) PVs that contain the PV prefix for a set of other PVs.  These are used to configure TomoScan to control a particular 
   areaDetector camera, etc.  Examples are (P)$(R)CameraPVPrefix and $(P)$(R)FilePluginPVPrefix.  
   These have the following properties:

  - They contain the string "PVPrefix" in their PV names.
  - They are saved by autosave in the auto_settings.sav file.
  - They are **not** saved by TomoScan in configuration files. 
  - They appear as normal lines in the file, not in comment lines.

4) PVs that are required by TomoScan, but which should not be saved and restored by autosave, either because
   they are read-only, or because writing to them when the IOC starts might have unwanted consequences.
   These have the following properties:

  - They appear in comment lines in the file.  The comment line must start with the string #controlPV followed by the PV name.
  - They do **not** contain the string "PVName" or "PVPrefix" in their PV names.
  - They are **not** saved by autosave in the auto_settings.sav file.
  - They are **not** saved by TomoScan in configuration files. 

When the request files above are read they are used to construct all of the EPICS PV names that are used by TomoScan.
This allows TomoScan to avoid having any hard-coded PV names, and makes it easy to port to a new beamline.

After creating the TomoScan13BM object in the line shown above it is ready to perform scans that are 
initiated by the $(P)$(R)StartScan PV from any Channel Access client.

The following two commands will run scans from the Python prompt.

::

>>> ts.fly_scan()

The above line runs the TomoScan.fly_scan() function in the Python main thread.  This means that the Python command
line will not be available until the scan completes.  The scan can be aborted by typing ^C.

>>> ts.run_fly_scan()

The above line runs the TomoScan.fly_scan() function in a new Python thread.  This means that the Python command
line is available immediately.  The scan can be aborted by typing ^C or by typing the command ``ts.abort_scan()``.

The base class implementation of fly_scan does the common operations required for a tomography dataset:

- Calls the begin_scan() method to perform whatever operations are required before the scan. 
  begin_scan has an implementation in the base class, but will commonly also be implemented in the derived class.
  The derived class will normally call the base class to perform the operations that are not beamline-specific. 
- Closes the shutter and collects the dark fields by calling the collect_dark+fields() method in the derived class. 
  This can be done before the scan, after the scan, both before and after, or never.
- Opens the shutter, moves the sample out, and collects the flat fields by calling the collect_flat_fields() method in the derived class. 
  This can be done before the scan, after the scan, both before and after, or never.
- Moves the sample in and calls the collect_projections() method in the derived class.  
  This method waits for the data collection to complete.
- Calls the end_scan() method to do any post-scan operations required.
  These may include moving the rotation stage back to the start position, putting the camera in Continuous mode, etc.
  end_scan has an implementation in the base class, but will commonly also be implemented in the derived class.
  The derived class will normally call the base class to perform the operations that are not beamline-specific. 
