"""Software for tomography scanning with EPICS at APS beamline 7-BM-B

   Classes
   -------
   TomoScan7BM
     Derived class for tomography scanning with EPICS at APS beamline 7-BM-B
"""
import time
import os
import math
import h5py 
from pathlib import Path
import numpy as np
from epics import PV

from tomoscan import TomoScanPSO
from tomoscan import log

EPSILON = .001

class TomoScan7BM(TomoScanPSO):
    """Derived class used for tomography scanning with EPICS at APS beamline 7-BM-B

    Parameters
    ----------
    pv_files : list of str
        List of files containing EPICS pvNames to be used.
    macros : dict
        Dictionary of macro definitions to be substituted when
        reading the pv_files
    """

    def __init__(self, pv_files, macros):
        super().__init__(pv_files, macros)
        
        # Set the detector running in FreeRun mode
        self.set_trigger_mode('FreeRun', 1)
        
        # Set data directory
        file_path = Path(self.epics_pvs['DetectorTopDir'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True))
        file_path = file_path.joinpath(self.epics_pvs['ExperimentYearMonth'].get(as_string=True) + '-'
                                       + self.epics_pvs['UserLastName'].get(as_string=True) + '-'
                                       + self.epics_pvs['ProposalNumber'].get(as_string=True)) 
        self.epics_pvs['FilePath'].put(str(file_path), wait=True)

        # Enable auto-increment on file writer
        self.epics_pvs['FPAutoIncrement'].put('Yes')

        # Eable over-writing warning
        self.epics_pvs['OverwriteWarning'].put('Yes')

    def open_shutter(self):
        """Opens the shutter to collect flat fields or projections.

        This does the following:

        - Checks if we are in testing mode.  If we are, do nothing.

        - Calls the base class method.

        - Opens the 2-BM-A fast shutter.
        """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not opening shutters.')
            return
        # Call the base class method
        super().open_shutter()
        # Open 7-BM-B fast shutter
        if not self.epics_pvs['OpenFastShutter'] is None:
            pv = self.epics_pvs['OpenFastShutter']
            value = self.epics_pvs['OpenFastShutterValue'].get(as_string=True)
            log.info('open fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['OpenFastShutter'].put(value, wait=True)

    def close_shutter(self):
        """Closes the shutter to collect dark fields.
        This does the following:

        - Checks if we are in testing mode.  If we are, do nothing

        - Calls the base class method.

        - Closes the 7-BM-B fast shutter.

       """
        if self.epics_pvs['Testing'].get():
            log.warning('In testing mode, so not closing shutters.')
            return
        # Call the base class method
        super().close_shutter()
        # Close 7-BM-B fast shutter
        if not self.epics_pvs['CloseFastShutter'] is None:
            pv = self.epics_pvs['CloseFastShutter']
            value = self.epics_pvs['CloseFastShutterValue'].get(as_string=True)
            log.info('close fast shutter: %s, value: %s', pv, value)
            self.epics_pvs['CloseFastShutter'].put(value, wait=True)

    def end_scan(self):
        """Performs the operations needed at the very end of a scan.

        This does the following:

        - Add theta to the raw data file. 

        - Close the shutter

        - Calls the base class method.
        """
        log.info('end scan')

        # Close the shutter
        self.close_shutter()

        # Add theta in the hdf file
        self.add_theta()

        # Call the base class method
        super().end_scan()


    def add_theta(self):
        """Add theta at the end of a scan.
        """
        log.info('add theta')
        self.theta = np.linspace(self.rotation_start, self.rotation_stop, self.num_angles)
        full_file_name = self.epics_pvs['FPFullFileName'].get(as_string=True)
        print(full_file_name)
        file_name_path = Path(full_file_name)
        for i in file_name_path.parent.iterdir():
            print(i)
        if os.path.exists(full_file_name):
            try:
                f = h5py.File(full_file_name, "a")
                with f:
                    try:
                        if self.theta is not None:
                            theta_ds = f.create_dataset('/exchange/theta', data = self.theta)
                    except:
                        log.error('Add theta: Failed accessing: %s', full_file_name)
                        traceback.print_exc(file=sys.stdout)
            except OSError:
                log.error('Add theta aborted')
        else:
            log.error('Failed adding theta. %s file does not exist', full_file_name)
