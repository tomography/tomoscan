=====
About
=====

:author: Mark Rivers (University of Chicago), Francesco De Carlo (Advanced Photon Source)

.. _2bm-tomo: https://github.com/xray-imaging/2bm-tomo

- tomoscan is a Python module for collecting computed tomography data at the APS. 
- tomoscan.py implements a base class (TomoScan) with the code that should be beamline-independent.  
- Beamline-dependent code is implemented in derived classes that inherit from tomoscan.

  - tomoscan_13bm.py is an implementation of the derived class TomoScan13BM. This is used at APS beamline 13-BM-D.
  - tomoscan_2bm.py is an implementation of the derived class TomoScan2BM. This is used at APS beamline 2-BM-A.


Advantages compared to current APS tomography Python software
=============================================================

The following describes some of the advantages of ``tomoscan`` compared to the existing 
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
  The configuration file itself does not even need to be created, it is simply
  the existing EPICS autosave request file for the tomography database.

  - The existing software hard-codes the PV prefixes in the Python code. This
    requires many changes in the code when porting to a new beamline.

- tomoscan can collect a scan in 3 modes:

  - In the main Python thread.  While the scan is running the Python prompt is not available.
  - In a separate Python thread.  While the scan is running the Python prompt is available.
  - Acting as a **tomography scan server**.  tomoscan itself only implements the code
    to collect a single tomography dataset, including dark-fields, flat-fields, and projections.
    Writing to the EPICS PV ``StartScan`` tells tomoscan to collect a new dataset in a separate Python
    thread.  ``StartScan`` is an EPICS busy record, so a client can do a ca_put_callback to wait
    for the scan to complete.  There are other PVs that indicate the status and progress of the scan.
    Thus, any EPICS client can be used to create complex scans, and this code does not need to be
    in the same Python process that is running tomoscan.  Possible clients include OPI displays
    such as medm, Python, IDL, the EPICS sscan record, SPEC, Bluesky, etc.

    - The existing software requires that scans be run from within the same Python process that is running
      the tomography scan.

- tomoscan is quite compact code. The base tomoscan class is ~810 lines, and the derived class for 13-BM
  is ~230 lines. Thus only a small amount of code needs to be copied and modified for a new beamline.
  This code collects a complete tomography dataset, including dark-fields, flat-fields, projections, 
  and saves a configuration file in JSON format at the end of the scan.
  The configuration file can be read back in to repeat the same scan at a future time.

  - The existing software is over 2,000 lines, much of which needs modification for a new beamline.
