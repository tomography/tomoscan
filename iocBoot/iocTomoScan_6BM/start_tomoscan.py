# This script creates an object of type TomoScan6BM for doing tomography scans at APS beamline 6-BM
# To run this script type the following:
#     python -i start_tomoscan.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_6bm import TomoScan6BM
ts = TomoScan6BM(["../../db/tomoScan_settings.req",
                  "../../db/tomoScan_6BM_settings.req"], 
                 {"$(P)":"6bmb:", "$(R)":"TomoScan:"})