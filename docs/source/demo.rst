=================
Demonstation code
=================

scan_demo.py
------------

:download:`scan_demo.py <../../demo/scan_demo.py>` is a simple program that demonstates 
scanning an EPICS PV and collecting a complete tomography dataset at each point in the scan.  
The EPICS PV to be scanned could be anything, such as the sample height, sample temperature, etc.

The following shows how the program is run, and the output.  In this case EPICS motor 13BMD:m90
was scanned from position 5.0, incrementing by 0.5, for 5 points:

  >>> from scan_demo import scan_demo
  >>> scan_demo('TSTest:TS1:', .01, '13BMD:m90', 5, 0.5, 5)
  Completed scan 1
  Completed scan 2
  Completed scan 3
  Completed scan 4
  Completed scan 5
  >>>



Using the EPICS sscan record
-----------------------------

The same scan that was done in Python above can also be done using the EPICS sscan record.

The following is the medm screen for the sscan record during such a scan.  Motor 13BMD:m90
is being scanned, and TSTest:TS1:StartScan is the detector trigger.  The scan record thus
triggers a complete tomography scan at each point in the motor scan. 

.. image:: img/tomo_scanRecord.png
    :width: 60%
    :align: center
