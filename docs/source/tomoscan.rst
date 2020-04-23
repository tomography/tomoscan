tomoscan
========

:author: Mark Rivers (University of Chicago), 

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

The simulation driver-specific parameters are the following:

.. cssclass:: table-bordered table-striped table-hover
.. flat-table::
  :header-rows: 2
  :widths: 40 20 20 20


  * - **Parameter Definitions in simDetector.cpp and EPICS Record Definitions in simDetector.template**
  * - Description
    - drvInfo string
    - EPICS record name
    - EPICS record type
  * - Gain in the X direction
    - SIM_GAINX
    - $(P)$(R)GainX, $(P)$(R)GainX_RBV
    - ao, ai
  * - Gain in the Y direction
    - SIM_GAINY
    - $(P)$(R)GainY, $(P)$(R)GainY_RBV
    - ao, ai
  * - Gain of the red channel
    - SIM_GAIN_RED
    - $(P)$(R)GainRed, $(P)$(R)GainRed_RBV
    - ao, ai
  * - Gain of the green channel
    - SIM_GAIN_GREEN
    - $(P)$(R)GainGreen, $(P)$(R)GainGreen_RBV
    - ao, ai
  * - Gain of the blue channel
    - SIM_GAIN_BLUE
    - $(P)$(R)GainBlue, $(P)$(R)GainBlue_RBV
    - ao, ai
  * - The offset added to the image.
    - SIM_OFFSET
    - $(P)$(R)Offset, $(P)$(R)Offset_RBV
    - ao, ai
  * - The amount of random noise added to the image.
    - SIM_NOISE
    - $(P)$(R)Noise, $(P)$(R)Noise_RBV
    - ao, ai
  * - Set to 1 to reset image back to initial conditions
    - RESET_IMAGE
    - $(P)$(R)Reset, $(P)$(R)Reset_RBV
    - longout, longin
  * - Sets the simulation mode. Options are:

      - 0: LinearRamp (linear ramp)
      - 1: Peaks (Array of peaks)
      - 2: Sine (Sum or product of sine waves)
      - 3: Offset&Noise (Offset and noise only, fastest mode)
    - SIM_MODE
    - $(P)$(R)SimMode, $(P)$(R)SimMode_RBV
    - mbbo, mbbi
  * - **Parameters for Array of Peaks Mode**
  * - X location of the first peak centroid
    - SIM_PEAK_START_X
    - $(P)$(R)PeakStartX, $(P)$(R)PeakStartX_RBV
    - longout, longin
  * - Y location of the first peak centroid
    - SIM_PEAK_START_Y
    - $(P)$(R)PeakStartY, $(P)$(R)PeakStartY_RBV
    - longout, longin
  * - X width of the peaks
    - SIM_PEAK_WIDTH_X
    - $(P)$(R)PeakWidthX, $(P)$(R)PeakWidthX_RBV
    - longout, longin
  * - Y width of the peaks
    - SIM_PEAK_WIDTH_Y
    - $(P)$(R)PeakWidthY, $(P)$(R)PeakWidthY_RBV
    - longout, longin
  * - Number of peaks in X direction
    - SIM_PEAK_NUM_X
    - $(P)$(R)PeakNumX, $(P)$(R)PeakNumX_RBV
    - longout, longin
  * - Number of peaks in Y direction
    - SIM_PEAK_NUM_Y
    - $(P)$(R)PeakNumY, $(P)$(R)PeakNumY_RBV
    - longout, longin
  * - X step between peaks
    - SIM_PEAK_STEP_X
    - $(P)$(R)PeakStepX, $(P)$(R)PeakStepX_RBV
    - longout, longin
  * - Y step between peaks
    - SIM_PEAK_STEP_Y
    - $(P)$(R)PeakStepY, $(P)$(R)PeakStepY_RBV
    - longout, longin
  * - Used to introduce randomness in the peak height. If non-zero then each gaussian
      peak in the array is assigned a scaling factor::

        scalingFactor = 1.0 + (rand() % peakVariation + 1) / 100.0
    - SIM_PEAK_HEIGHT_VARIATION
    - $(P)$(R)PeakVariation, $(P)$(R)PeakVariation_RBV
    - longout, longin
  * - **Parameters for Sine Mode**
  * - The operation to use to combine XSine1 and XSine2. Choices are:

      - 0: Add
      - 1: Multiply
    - SIM_XSIN_OPERATION
    - $(P)$(R)XSineOperation, $(P)$(R)XSineOperation_RBV
    - mbbo, mbbi
  * - The operation to use to combine YSine1 and YSine2. Choices are:

      - 0: Add
      - 1: Multiply
    - SIM_YSIN_OPERATION
    - $(P)$(R)YSineOperation, $(P)$(R)YSineOperation_RBV
    - mbbo, mbbi
  * - The amplitude of the sine wave. There is a record for each of the 4 sine waves:
      XSine1, XSine2, YSine1, YSine2.
    - SIM_[X,Y]SIN[1,2]_AMPLITUDE
    - $(P)$(R)[X,Y]Sine[1,2]Amplitude, $(P)$(R)[X,Y]Sine[1,2]Amplitude_RBV
    - ao, ai
  * - The frequency of the sine wave. A frequency of 1 means there is one complete period
      of the sine wave across the image in the X or Y direction. There is a record for
      each of the 4 sine waves: XSine1, XSine2, YSine1, YSine2.
    - SIM_[X,Y]SIN[1,2]_FREQUENCY
    - $(P)$(R)[X,Y]Sine[1,2]Frequency, $(P)$(R)[X,Y]Sine[1,2]Frequency_RBV
    - ao, ai
  * - The phase of the sine wave in degrees. A phase of 90 is the same as a cosine wave.
      There is a record for each of the 4 sine waves: XSine1, XSine2, YSine1, YSine2.
    - SIM_[X,Y]SIN[1,2]_PHASE
    - $(P)$(R)[X,Y]Sine[1,2]Phase, $(P)$(R)[X,Y]Sine[1,2]Phase_RBV
    - ao, ai


Screenshots
------------

simDetector.adl
~~~~~~~~~~~~~~~

The following is the MEDM screen simDetector.adl for the simulation
detector.

.. image:: simDetector.png
    :width: 75%
    :align: center

Linear Ramp Mode
~~~~~~~~~~~~~~~~

The following is an IDL `epics_ad_display`_ screen using `image_display`_ to
display the simulation detector in monochrome linear ramp mode.

IDL epics_ad_display.pro display of simulation detector in monochrome

.. image:: simDetector_image_display.png
    :width: 75%
    :align: center

Ramp Mode
~~~~~~~~~

The following is an ImageJ plugin `EPICS_AD_Viewer`_ screen
displaying the simulation detector in color linear ramp mode.

ImageJ EPICS_AD_Viewer display of simulation detector in color linear

.. image:: simDetector_ImageJ_display.png
    :width: 60%
    :align: center

Simulation setup screen with Peaks mode selected
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is an example of the MEDM screen that provides access to the
specific parameters for the simulation detector. In this case Peaks
mode is selected.

.. image:: simDetectorSetupPeaks.png
    :width: 100%
    :align: center

ImageJ display with the above Peaks mode parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: simDetectorImagePeaks.png
    :width: 50%
    :align: center

Simulation setup screen with simple Sine mode setup
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is a simple example of Sine mode. The ``XSine1`` frequency is 2 and
the ``YSine1`` frequency is 4. The ``Sine2`` amplitudes are zero, so there is
a single sine wave in each direction.

.. image:: simDetectorSetupSimpleSine.png
    :width: 100%
    :align: center

ImageJ display with the above simple Sine mode parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: simDetectorImageSimpleSine.png
    :width: 50%
    :align: center

This is a complex example of Sine mode. There are 2 sine waves in each
direction, with multiplication in X and addition in Y.

Simulation setup screen with complex Sine mode parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: simDetectorSetupComplexSine.png
    :width: 100%
    :align: center

ImageJ display with the above complex Sine mode parameters
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: simDetectorImageComplexSine.png
    :width: 50%
    :align: center

ImageJ X profile with the above complex Sine mode parameters.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: simDetectorXProfileComplexSine.png
    :width: 75%
    :align: center

ImageJ Y profile with the above complex Sine mode parameters.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: simDetectorYProfileComplexSine.png
    :width: 75%
    :align: center

Simulation setup screen with Sine mode parameters in RGB1 color mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This is a example of Sine mode in RGB1 color mode.

+ The red signal is controlled by a horizontal sine wave with a
  frequency of 2 and a phase of 90 degrees.
+ The green signal is controlled by a vertical sine wave with a
  frequency of 4 and a phase of 45 degrees.
+ The blue signal is controlled by the sum of sine waves in the
  horizontal with a frequency of 5 and in the vertical with a frequency
  of 20.

.. image:: simDetectorSetupColorSine.png
    :width: 100%
    :align: center

ImageJ display with the above color Sine mode parameters.
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: simDetectorImageColorSine.png
    :width: 50%
    :align: center
