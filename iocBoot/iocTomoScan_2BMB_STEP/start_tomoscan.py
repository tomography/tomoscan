# This script creates an object of type TomoScan2BM for doing tomography scans at APS beamline 2-BM-A
# To run this script type the following:
#     python -i start_tomoscan_2bm.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_2bm_step import TomoScan2BMSTEP
ts = TomoScan2BMSTEP(["../../db/tomoScan_settings.req",
                  "../../db/tomoScan_step_settings.req",
                  "../../db/tomoScan_2BM_settings.req"], 
                 {"$(P)":"2bmb:", "$(R)":"TomoScanStep:"})
