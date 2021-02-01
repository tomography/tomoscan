TOP=../..

include $(TOP)/configure/CONFIG
#----------------------------------------
#  ADD MACRO DEFINITIONS BELOW HERE

# Build the IOC application
PROD_IOC = tomoScanApp

# tomoScanApp.dbd will be created and installed
DBD += tomoScanApp.dbd

# test.dbd will include these files:
tomoScanApp_DBD += base.dbd
tomoScanApp_DBD += asyn.dbd drvAsynIPPort.dbd
tomoScanApp_DBD += busySupport.dbd
tomoScanApp_DBD += asSupport.dbd

# tomoScanApp_registerRecordDeviceDriver.cpp derives from test.dbd
tomoScanApp_SRCS += tomoScanApp_registerRecordDeviceDriver.cpp

# Build the main IOC entry point where needed
tomoScanApp_SRCS_DEFAULT += tomoScanMain.cpp
tomoScanApp_SRCS_vxWorks += -nil-

tomoScanApp_LIBS += autosave
tomoScanApp_LIBS += busy
tomoScanApp_LIBS += asyn

# Finally link IOC to the EPICS Base libraries
tomoScanApp_LIBS += $(EPICS_BASE_IOC_LIBS)

include $(TOP)/configure/RULES
#----------------------------------------
#  ADD EXTRA GNUMAKE RULES BELOW HERE
