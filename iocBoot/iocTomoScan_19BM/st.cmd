< envPaths

epicsEnvSet("P", "19bm:")
epicsEnvSet("R", "TomoScan:")

## Register all support components

# Use these lines to run the locally built tomoScanApp
dbLoadDatabase "../../dbd/tomoScanApp.dbd"
tomoScanApp_registerRecordDeviceDriver pdbbase

# Connect to the Aerotech controller
# 19-BM inherits the rotary stage and its Aerotech Ensemble controller from
# 7-BM, where the controller answered on 164.54.107.56:8001.  The hardware is
# unchanged; only the address changes when it is re-racked here.
# TODO: replace with the 19-BM address once the controller is on the network.
drvAsynIPPortConfigure("PSO_PORT", "0.0.0.0:8001", 0, 0, 0)
asynOctetSetInputEos(PSO_PORT, 0, "\n")
asynOctetSetOutputEos(PSO_PORT, 0, "\n")
asynSetTraceIOMask(PSO_PORT, 0, ESCAPE)
asynSetTraceMask(PSO_PORT, 0, DRIVER|ERROR)

dbLoadTemplate("tomoScan.substitutions")

< save_restore.cmd
save_restoreSet_status_prefix($(P))
dbLoadRecords("$(AUTOSAVE)/asApp/Db/save_restoreStatus.db", "P=$(P)")

iocInit

create_monitor_set("auto_settings.req", 30, "P=$(P),R=$(R)")
