# This script creates an object of type TomoScan6BM_PSO for doing tomography scans at APS beamline 6-BM-B
# To run this script type the following:
#     python -i start_tomoscan.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_13bm_pso import TomoScan13BM_PSO
ts = TomoScan6BMB_PSO(["../../db/tomoScan_settings.req",
                       "../../db/tomoScan_PSO_settings.req", 
                       "../../db/tomoScan_PCO_settings.req", 
                       "../../db/tomoScan_6BMB_settings.req"], 
                      {"$(P)":"6BMB_LVPPS1:", "$(R)":"TS:"})
