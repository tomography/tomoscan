# This script creates an object of type TomoScanStream32ID for doing tomography scans at APS beamline 32ID
# To run this script type the following:
#     python -i start_tomoscan_stream_2bm.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_stream_32id import TomoScanStream32ID
ts = TomoScanStream32ID(["../../db/tomoScan_settings.req",
                        "../../db/tomoScan_PSO_settings.req", 
                        "../../db/tomoScanStream_settings.req",
                        "../../db/tomoScan_32ID_settings.req"],
                        {"$(P)":"32id:", "$(R)":"TomoScanStream:"})