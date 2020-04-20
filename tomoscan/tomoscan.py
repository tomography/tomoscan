from epics import PV
import json

class tomoscan:

  def __init__(self, autoSettingsFile, macros=[]):
    self.configPVs = {}
    self.controlPVs = {}
    if (autoSettingsFile != None):
      self.readAutoSettingsFile(autoSettingsFile, macros)

    self.epicsPVs = {**self.configPVs, **self.controlPVs}

  def showPVs(self):
    print("configPVS:")
    for pv in self.configPVs:
      print(pv, ":", self.configPVs[pv].get(as_string=True))

    print("")
    print("controlPVS:")
    for pv in self.controlPVs:
      print(pv, ":", self.controlPVs[pv].get(as_string=True))

  def readAutoSettingsFile(self, autoSettingsFile, macros):
    f = open(autoSettingsFile)
    lines = f.read()
    f.close()
    lines = lines.splitlines()
    for line in lines:
      # Remove trailing newline
      line = line.rstrip("\n")
      pvname = line
      # Do macro substitution
      for key in macros:
         pvname = pvname.replace(key, macros[key])
      dictentry = line
      for key in macros:
         dictentry = dictentry.replace(key, "")
      pv = PV(pvname)
      self.configPVs[dictentry] = pv
      if (dictentry.find("PVName") != -1):
        pvname = pv.value
        dictentry = dictentry.strip("PVName")
        self.controlPVs[dictentry] = PV(pvname)

  def moveSampleIn(self):
    axis = self.epicsPVs["FlatFieldAxis"].char_value
    print("moveSampleIn axis:", axis)
    if (axis == "X") or (axis == "Both"):
      position = self.epicsPVs["SampleInX"].value
      self.epicsPVs["SampleX"].put(position, wait=True)
      
    if (axis == "Y") or (axis == "Both"):
      position = self.epicsPVs["SampleInY"].value
      self.epicsPVs["SampleY"].put(position, wait=True)

  def moveSampleOut(self):
    axis = self.epicsPVs["FlatFieldAxis"].char_value
    print("moveSampleOut axis:", axis)
    if (axis == "X") or (axis == "Both"):
      position = self.epicsPVs["SampleOutX"].value
      self.epicsPVs["SampleX"].put(position, wait=True)
      
    if (axis == "Y") or (axis == "Both"):
      position = self.epicsPVs["SampleOutY"].value
      self.epicsPVs["SampleY"].put(position, wait=True)

  def saveConfiguration(self, fileName):
    d = {}
    for pv in self.configPVs:
      d[pv] = self.configPVs[pv].char_value
    f = open(fileName, "w")
    json.dump(d, f, indent=2)
    f.close()
  
  def loadConfiguration(self, fileName):
    f = open(fileName, "r")
    d = json.load(f)
    f.close()
    for pv in d:
      self.configPVs[pv].put(d[pv])
