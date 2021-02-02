< envPaths

epicsEnvSet("P", "2bmb:")
epicsEnvSet("R", "TomoScan:")

## Register all support components

# Use these lines to run the locally built tomoScanApp
dbLoadDatabase "../../dbd/tomoScanApp.dbd"
tomoScanApp_registerRecordDeviceDriver pdbbase

# Connect to the Aerotech controller
drvAsynIPPortConfigure("PSO_PORT", "164.54.113.74:8000", 0, 0, 0)
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
