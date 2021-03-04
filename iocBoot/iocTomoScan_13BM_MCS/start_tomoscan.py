# This script creates an object of type TomoScan13BM_PSO for doing tomography scans at APS beamline 13-BM-D
# To run this script type the following:
#     python -i start_tomoscan.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_13bm_mcs import TomoScan13BM_MCS
ts = TomoScan13BM_MCS(["../../db/tomoScan_settings.req",
                       "../../db/tomoScan_13BM_MCS_settings.req", 
                       "../../db/tomoScan_13BM_settings.req"], 
                      {"$(P)":"13BMDPG2:", "$(R)":"TS:"})
