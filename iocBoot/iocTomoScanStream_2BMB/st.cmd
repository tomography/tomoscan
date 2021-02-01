< envPaths

epicsEnvSet("P", "2bmb:")
epicsEnvSet("R", "TomoScanStream:")

## Register all support components

# Use these lines to run the locally built tomoScanApp
dbLoadDatabase "../../dbd/tomoScanApp.dbd"
tomoScanApp_registerRecordDeviceDriver pdbbase

# Use these lines to run the xxx application on APSshare.
#dbLoadDatabase "/APSshare/epics/synApps_6_1/support/xxx-R6-1/dbd/iocxxxLinux.dbd"
#iocxxxLinux_registerRecordDeviceDriver pdbbase


dbLoadTemplate("tomoScanStream.substitutions")

< save_restore.cmd
save_restoreSet_status_prefix($(P))
dbLoadRecords("$(AUTOSAVE)/asApp/Db/save_restoreStatus.db", "P=$(P)")

iocInit

create_monitor_set("auto_settings.req", 30, "P=$(P),R=$(R)")
