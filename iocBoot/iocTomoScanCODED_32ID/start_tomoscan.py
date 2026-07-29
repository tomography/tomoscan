# This script creates an object of type TomoScan2BM for doing tomography scans at APS beamline 2-BM-A
# To run this script type the following:
#     python -i start_tomoscan_2bm.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_coded_32id import TomoScanCODED32ID
ts = TomoScanCODED32ID(["../../db/tomoScan_settings.req",
                  "../../db/tomoScan_PSO_settings.req",
                  "../../db/tomoScan_32ID_settings.req",
                  "../../db/tomoScan_CODED_settings.req"],
                 {"$(P)":"32id:", "$(R)":"TomoScanCODED:"})