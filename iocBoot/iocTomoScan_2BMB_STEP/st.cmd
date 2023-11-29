< envPaths

epicsEnvSet("P", "2bmb:")
epicsEnvSet("R", "TomoScanStep:")

## Register all support components

# Use these lines to run the locally built tomoScanApp
dbLoadDatabase "../../dbd/tomoScanApp.dbd"
tomoScanApp_registerRecordDeviceDriver pdbbase

dbLoadTemplate("tomoScan.substitutions")

< save_restore.cmd
save_restoreSet_status_prefix($(P))
dbLoadRecords("$(AUTOSAVE)/asApp/Db/save_restoreStatus.db", "P=$(P)")

iocInit

create_monitor_set("auto_settings.req", 30, "P=$(P),R=$(R)")
