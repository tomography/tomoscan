# This script creates an object of type TomoScanStream7BM for doing tomography scans at APS beamline 2-BM-A
# To run this script type the following:
#     python -i start_tomoscan_stream_7bm.py
# The -i is needed to keep Python running, otherwise it will create the object and exit
from tomoscan.tomoscan_stream_7bm import TomoScanStream7BM
ts = TomoScanStream7BM(["../../db/tomoScan_settings.req",
                        "../../db/tomoScan_PSO_settings.req", 
                        "../../db/tomoScanStream_settings.req",
                        "../../db/tomoScan_7BM_settings.req"], 
                        {"$(P)":"7bmtomo:", "$(R)":"TomoScanStream:"})
