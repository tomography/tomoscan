========
tomoscan
========

**tomoscan** is a package for collecting computed tomography data at the APS.

It provides 2 Python modules:
- **tomoscan** is a module that implements the Python class TomoScan for collecting computed tomography data
using the EPICS control system. This base class should be beamline-independent.  
- **tomoscan_13bm** is a module that implements the derived class TomoScan13BM that is specific to APS beamline 13-BM-D. 

It also provides an EPICS support module, including databases, OPI screens, and an example IOC application that can be
used to run those databases.

Documentation: https://tomoscan.readthedocs.io
