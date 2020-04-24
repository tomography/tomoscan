import epics

def scanDemo(tomoPrefix, tomoTime, scanPV, start, step, points):

    epics.caput(tomoPrefix + 'ExposureTime', tomoTime, wait=True)
    
    for i in range(1, points+1):
        epics.caput(scanPV, start + step*i, wait=True)
        epics.caput(tomoPrefix + 'FileName', 'Test_'+str(1), wait=True, timeout=100)
        epics.caput(tomoPrefix + 'StartScan', 1, wait=True, timeout=100)
        print('Completed scan', i)
