# This script creates an object of type TomoScanFPGA32ID for doing tomography scans
# at APS beamline 32-ID using the softGlueZynq FPGA for interlaced trigger generation.
# To run this script type the following:
#     python -i start_tomoscan.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_fpga_32id import TomoScanFPGA32ID
ts = TomoScanFPGA32ID(["../../db/tomoScan_settings.req",
                       "../../db/tomoScan_PSO_settings.req",
                       "../../db/tomoScan_32ID_settings.req",
                       "../../db/tomoScan_FPGA_settings.req"],
                      {"$(P)": "32id:", "$(R)": "TomoScanFPGA:"})
