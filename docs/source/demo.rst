=================
Demonstation code
=================

scan_demo.py
------------

scan_demo.py is a simple program that demonstrates 
scanning an EPICS PV and collecting a complete tomography dataset at each point in the scan.  
The EPICS PV to be scanned could be anything, such as the sample height, sample temperature, etc.

.. literalinclude:: ../../demo/scan_demo.py

The following shows how the program is run, and the output.  In this case EPICS motor 13BMD:m90
was scanned from position 5.0, incrementing by 1.0, for 5 points:

>>> from scan_demo import scan_demo
>>> scan_demo('13BMDPG1:TS:', .01, '13BMD:m90', 5, 1, 5)
Completed dataset T:\tomo_user\2020\Run1\Test\Test_R_001.h5
Completed dataset T:\tomo_user\2020\Run1\Test\Test_R_002.h5
Completed dataset T:\tomo_user\2020\Run1\Test\Test_R_003.h5
Completed dataset T:\tomo_user\2020\Run1\Test\Test_R_004.h5
Completed dataset T:\tomo_user\2020\Run1\Test\Test_R_005.h5

Using the EPICS sscan record
-----------------------------

The same scan that was done in Python above can also be done using the EPICS sscan record.

The following is the medm screen for the sscan record during such a scan.  Motor 13BMD:m90
is being scanned, and TSTest:TS1:StartScan is the detector trigger.  The scan record thus
triggers a complete tomography scan at each point in the motor scan. 

.. image:: img/tomo_scanRecord.png
    :width: 60%
    :align: center

Using the tomoscan-cli
----------------------

The same scan that was done in Python above can also be done using the tomoscan-cli::

    $ tomoscan single

tomoscan supports also vertical, horizontal and mosaic tomographic scans with::

    $ tomoscan vertical
    $ tomoscan horizontal
    $ tomoscan mosaic

to run a vertical scan::

    $ tomoscan vertical --vertical-start 0 --vertical-step-size 0.1 --vertical-steps 2

    2020-05-19 18:53:49,311 - set trigger mode: FreeRun
    2020-05-19 18:53:49,473 - vertical scan start
    2020-05-19 18:53:49,474 - scan start
    2020-05-19 18:53:49,474 - vertical positions (mm): [0.  0.1]
    2020-05-19 18:53:49,475 - SampleY stage start position: 0.000 mm
    2020-05-19 18:53:54,461 - single scan start
    2020-05-19 18:53:54,462 - begin scan
    2020-05-19 18:53:55,029 - collect projections
    2020-05-19 18:53:55,029 - open shutter: <PV '2bma:A_shutter:open.VAL', count=1, type=time_enum, access=read/write>, value: 1
    2020-05-19 18:53:55,033 - open fast shutter: <PV '2bma:m23', count=1, type=time_double, access=read/write>, value: 1
    2020-05-19 18:53:56,152 - move_sample_in axis: X
    2020-05-19 18:53:57,332 - taxi before starting capture
    2020-05-19 18:53:59,969 - set trigger mode: PSOExternal
    2020-05-19 18:54:00,603 - start fly scan
    2020-05-19 18:54:23,462 - collect flat fields
    2020-05-19 18:54:23,462 - open shutter: <PV '2bma:A_shutter:open.VAL', count=1, type=time_enum, access=read/write>, value: 1
    2020-05-19 18:54:23,464 - open fast shutter: <PV '2bma:m23', count=1, type=time_double, access=read/write>, value: 1
    2020-05-19 18:54:23,467 - move_sample_out axis: X
    2020-05-19 18:54:24,461 - collect static frames: 20
    2020-05-19 18:54:24,462 - set trigger mode: Internal
    2020-05-19 18:54:25,386 - collect dark fields
    2020-05-19 18:54:25,387 - close shutter: <PV '2bma:A_shutter:close.VAL', count=1, type=time_enum, access=read/write>, value: 1
    2020-05-19 18:54:25,391 - close fast shutter: <PV '2bma:m23', count=1, type=time_double, access=read/write>, value: 0
    2020-05-19 18:54:26,493 - collect static frames: 10
    2020-05-19 18:54:26,494 - set trigger mode: Internal
    2020-05-19 18:54:27,376 - end scan
    2020-05-19 18:54:27,380 - add theta
    2020-05-19 18:54:27,385 - data save location: /local/data/    2020-05/empty_pi_last_name/vertical_030.h5
    2020-05-19 18:54:27,400 - set trigger mode: FreeRun
    2020-05-19 18:54:27,637 - move_sample_in axis: X
    2020-05-19 18:54:29,094 - Scan complete
    2020-05-19 18:54:29,095 - single scan time: 0.577 minutes
    2020-05-19 18:54:29,095 - SampleY stage start position: 0.100 mm
    2020-05-19 18:54:31,076 - single scan start
    2020-05-19 18:54:31,076 - begin scan
    2020-05-19 18:54:38,988 - collect projections
    2020-05-19 18:54:38,988 - open shutter: <PV '2bma:A_shutter:open.VAL', count=1, type=time_enum, access=read/write>, value: 1
    2020-05-19 18:54:38,990 - open fast shutter: <PV '2bma:m23', count=1, type=time_double, access=read/write>, value: 1
    2020-05-19 18:54:40,093 - move_sample_in axis: X
    2020-05-19 18:54:40,098 - taxi before starting capture
    2020-05-19 18:54:43,916 - set trigger mode: PSOExternal
    2020-05-19 18:54:44,553 - start fly scan
    2020-05-19 18:55:07,112 - collect flat fields
    2020-05-19 18:55:07,112 - open shutter: <PV '2bma:A_shutter:open.VAL', count=1, type=time_enum, access=read/write>, value: 1
    2020-05-19 18:55:07,114 - open fast shutter: <PV '2bma:m23', count=1, type=time_double, access=read/write>, value: 1
    2020-05-19 18:55:07,117 - move_sample_out axis: X
    2020-05-19 18:55:08,111 - collect static frames: 20
    2020-05-19 18:55:08,112 - set trigger mode: Internal
    2020-05-19 18:55:09,038 - collect dark fields
    2020-05-19 18:55:09,039 - close shutter: <PV '2bma:A_shutter:close.VAL', count=1, type=time_enum, access=read/write>, value: 1
    2020-05-19 18:55:09,050 - close fast shutter: <PV '2bma:m23', count=1, type=time_double, access=read/write>, value: 0
    2020-05-19 18:55:10,160 - collect static frames: 10
    2020-05-19 18:55:10,161 - set trigger mode: Internal
    2020-05-19 18:55:11,057 - end scan
    2020-05-19 18:55:11,061 - add theta
    2020-05-19 18:55:11,065 - data save location: /local/data/    2020-05/empty_pi_last_name/vertical_031.h5
    2020-05-19 18:55:11,067 - set trigger mode: FreeRun
    2020-05-19 18:55:11,318 - move_sample_in axis: X
    2020-05-19 18:55:12,777 - Scan complete
    2020-05-19 18:55:12,778 - single scan time: 0.695 minutes
    2020-05-19 18:55:12,783 - vertical scan time: 1.388 minutes
    2020-05-19 18:55:12,783 - vertical scan end

tomoscan-cli always stores the last used set of paramters so to repeat the above vertical scan::

    $ tomoscan vertical

use ``-h`` for the list of supported parameters.

To repeat the vertical scan 5 times with 60 s wait time between each::

    $ tomoscan vertical --sleep --sleep-steps 10 --sleep-time 60

to repeat the same::

    $ tomoscan vertical --sleep

while::

    $ tomoscan vertical

repeats a single vertical scan with --vertical-start 0 --vertical-step-size 0.1 --vertical-steps 5.

To reset the tomoscan-cli status::

	$ tomoscan init

after deleting the tomoscan.conf file if already exists.


