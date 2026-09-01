# This script creates an object of type TomoScan6BM_PSO for doing tomography scans at APS beamline 6-BM-B
# To run this script type the following:
#     python -i start_tomoscan.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_6bmb import TomoScan6BMB
ts = TomoScan6BMB(["../../db/tomoScan_settings.req",
                   "../../db/tomoScan_PSO_settings.req", 
                   "../../db/tomoScan_PCO_settings.req", 
                   "../../db/tomoScan_6BMB_settings.req"], 
                   {"$(P)":"6BMBTOMO:", "$(R)":"TS:"})
