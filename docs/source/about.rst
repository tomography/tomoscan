=====
About
=====

:author: Mark Rivers (University of Chicago)

.. _2bm-tomo: https://github.com/xray-imaging/2bm-tomo

tomoscan is a Python class for collecting computed tomography data at the APS. 
tomoscan.py implements a base class with the code that should be beamline-independent.  
Beamline-dependent code is implemented in derived classes that inherit from tomoscan.


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

- tomoscan will implement a **server mode**.  tomoscan itself only implements the code
  to collect a single tomography dataset, including dark-fields, flat-fields, and projections.
  The server mode will listen for EPICS PVs that command tomoscan to collect a new dataset.
  There will be a status PV that indicates the scan status, indicating when the scan is complete.
  Thus, any EPICS client can be used to create complex scans, and this code does not need to be
  in the same Python process that is running tomoscan.  Possible clients include Python, IDL,
  the EPICS sscan record, SPEC, etc.  **NOTE: the server mode is a planned feature and does not
  currently exist.**

  - The existing software requires that scans be run from within the same Python process that is running
    the tomography scan.

- tomoscan is very compact code, less than 400 lines, including the base tomoscan class (274 lines) 
  and the derived class for 13-BM (124 lines).  
  This code collects a complete tomography dataset, including dark-fields, flat-fields, projections, 
  and saves a configuration file in JSON format at the end of the scan.
  The configuration file can be read back in to repeat the same scan at a future time.

  - The existing software is over 2,000 lines.  However, it does have more functionality than tomoscan
    currently has. 