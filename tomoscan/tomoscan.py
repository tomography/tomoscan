from epics import PV

class tomoscan:

  def __init__(autoSettingsFile, macros=[]):
    configPVs = {}
    if (autoSettingsFile != None):
      parseAutoSettingsFile()

  def parseAutoSettingsFile(autoSettingsFile):
    
    lines = open(autoSettingsFile).readlines()
    close(autoSettingsFile)

    # Do macro substitution
    for key in macros:
      print("Replacing", key, "with", macros[key])
      lines = lines.replace(key, macros[key])
    
    for line in lines:
      configPVs[line] = PV(line)

    for pv in configPVs:
      print(pv, ":", configPVs[pv].get(as_string=True))
