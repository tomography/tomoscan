# This script creates an object of type TomoScan32IDC for doing tomography scans
# at APS beamline 32-ID-C (Micro-CT station).
# To run this script type the following:
#     python -i start_tomoscan.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_32idc import TomoScan32IDC
ts = TomoScan32IDC(["../../db/tomoScan_settings.req",
                    "../../db/tomoScan_PSO_settings.req",
                    "../../db/tomoScan_32IDC_settings.req"],
                   {"$(P)":"32idc:", "$(R)":"TomoScan:"})
