< envPaths

epicsEnvSet("P", "TSTest:")
epicsEnvSet("R", "TS1:")

## Register all support components
dbLoadDatabase "../../dbd/tomoScanApp.dbd"
tomoScanApp_registerRecordDeviceDriver pdbbase

dbLoadTemplate("tomoScan.substitutions")

< save_restore.cmd
save_restoreSet_status_prefix($(P))
dbLoadRecords("$(AUTOSAVE)/asApp/Db/save_restoreStatus.db", "P=$(P)")

iocInit

create_monitor_set("auto_settings.req", 30, "P=$(P),R=$(R)")
