# This script creates an object of type TomoScan7BM for doing tomography scans at APS beamline 7-BM-B
# To run this script type the following:
#     python -i start_tomoscan_7bm.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_7bm import TomoScan7BM
ts = TomoScan7BM(["../../db/tomoScan_settings.req",
                  "../../db/tomoScan_PSO_settings.req", 
                  "../../db/tomoScan_7BM_settings.req"], 
                 {"$(P)":"7bmtomo:", "$(R)":"TomoScan:"})
