# This script creates an object of type TomoScan2BM for doing tomography scans at APS beamline 2-BM-A
# To run this script type the following:
#     python -i start_tomoscan_2bm.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_2id_step import TomoScan2IDSTEP
ts = TomoScan2BMSTEP(["../../db/tomoScan_settings.req",
                  "../../db/tomoScan_step_settings.req",
                  "../../db/tomoScan_2ID_settings.req"], 
                 {"$(P)":"2id:", "$(R)":"TomoScanStep:"})
