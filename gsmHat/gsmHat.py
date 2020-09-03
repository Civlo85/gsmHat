#!/usr/bin/python3
# Filename: gsmHat.py
import logging
import serial
import threading
import time
import math
import re
from datetime import datetime
import RPi.GPIO as GPIO

class SMS:
    def __init__(self):
        self.Message = ''
        self.Sender = ''
        self.Receiver = ''
        self.Date = ''

class GPS:
    EarthRadius = 6371e3         # meters

    @staticmethod
    def CalculateDeltaP(Position1, Position2):
        phi1 = Position1.Latitude * math.pi / 180.0
        phi2 = Position2.Latitude * math.pi / 180.0
        deltaPhi = (Position2.Latitude - Position1.Latitude) * math.pi / 180.0
        deltaLambda = (Position2.Longitude - Position1.Longitude) * math.pi / 180.0

        a = math.sin(deltaPhi / 2) * math.sin(deltaPhi / 2) + math.cos(phi1) * math.cos(phi2) * math.sin(deltaLambda / 2) * math.sin(deltaLambda / 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        d = GPS.EarthRadius * c    # in meters

        return d

    def __init__(self):
        self.GNSS_status = 0
        self.Fix_status = 0
        self.UTC = ''           # yyyyMMddhhmmss.sss
        self.Latitude = 0.0     # ±dd.dddddd            [-90.000000,90.000000]
        self.Longitude = 0.0    # ±ddd.dddddd           [-180.000000,180.000000]
        self.Altitude = 0.0     # in meters
        self.Speed = 0.0        # km/h [0,999.99]
        self.Course = 0.0       # degrees [0,360.00]
        self.HDOP = 0.0         # [0,99.9]
        self.PDOP = 0.0         # [0,99.9]
        self.VDOP = 0.0         # [0,99.9]
        self.GPS_satellites = 0 # [0,99]
        self.GNSS_satellites = 0    # [0,99]
        self.Signal = 0.0         # %      max = 55 dBHz

class GSMHat:
    """GSM Hat Backend with SMS Functionality (for now)"""
    
    regexGetSingleValue = r'([+][a-zA-Z\ ]+(:\ ))([\d]+)'
    regexGetAllValues = r'([+][a-zA-Z:\s]+)([\w\",\s+\/:.]+)'
    timeoutSerial = 5
    timeoutGPSActive = 1
    timeoutGPSInactive = 5

    def __init__(self, SerialPort, Baudrate):
        self.__baudrate = Baudrate
        self.__port = SerialPort

        self.__logger = logging.getLogger(__name__)
        self.__logger.setLevel(logging.INFO)
        self.__loggerFileHandle = logging.FileHandler('gsmHat.log')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.__loggerFileHandle.setFormatter(formatter)
        self.__loggerFileHandle.setLevel(logging.INFO )
        self.__logger.addHandler(self.__loggerFileHandle)

        self.__connect()
        self.__startWorking()
    
    def __connect(self):
        self.__ser = serial.Serial(self.__port, self.__baudrate)
        self.__ser.flushInput()
        self.__serData = ''
        self.__writeLock = False
        self.__logger.info('Serial connection to '+self.__port+' established')

    def __disconnect(self):
        self.__ser.close()
    
    def __startWorking(self):
        self.__working = True
        self.__state = 1
        self.__smsToRead = 0
        self.__init = False
        self.__readRAW = False
        self.__smsToBuild = None
        self.__smsList = []
        self.__smsSendList = []
        self.__numberToCall = ''
        self.__sendHangUp = False
        self.__startGPS = False
        self.__GPSstarted = False
        self.__GPSstartSending = False
        self.__GPSstopSending = False
        self.__GPScollectData = False
        self.__GPSactualData = GPS()
        self.__GPStimeout = self.timeoutGPSInactive * 1000
        self.__GPSwaittime = 0
        self.__workerThread = threading.Thread(target=self.__workerThread, daemon=True)
        self.__workerThread.start()

    def __stopWorking(self):
        self.__working = False
        self.__workerThread.join(10.0)  # Timeout = 10.0 Seconds

    def __sendToHat(self, string):
        if self.__writeLock == False:
            self.__lastCommand = string
            string = string + '\n'
            self.__ser.write(string.encode('iso-8859-1'))
            self.__writeLock = True
            self.__sentTimeout = int(round(time.time())) + self.timeoutSerial
            self.__logger.debug('Sent to hat: %s' % string)
            return True
        else:
            self.__logger.debug('Wait for Lock...')
            time.sleep(1)
            return False
    
    def __pressPowerKey(self):
        GPIO.setmode(GPIO.BOARD)
        GPIO.setup(7, GPIO.OUT)
        while True:
            GPIO.output(7, GPIO.LOW)
            time.sleep(4)
            GPIO.output(7, GPIO.HIGH)
            break
        GPIO.cleanup()
        time.sleep(10)

    def SMS_available(self):
        return len(self.__smsList)
        
    def SMS_read(self):
        if self.SMS_available() > 0:
            retSMS = self.__smsList[0]
            del self.__smsList[0]
            return retSMS

        return None

    def SMS_write(self, NumberReceiver, Message):
        newSMS = SMS()
        newSMS.Receiver = NumberReceiver
        newSMS.Message = Message
        self.__smsSendList.append(newSMS)

    def Call(self, Number, Timeout = 15):
        if self.__numberToCall == '':
            self.__numberToCall = str(Number)
            self.__callTimeout = Timeout
            return True

        return False

    def HangUp(self):
        self.__sendHangUp = True

    def GetActualGPS(self):
        return self.__GPSactualData

    def __startGPSUnit(self):
        self.__startGPS = True
    
    def __startGPSsending(self):
        self.__GPSstartSending = True

    def __stopGPSsending(self):
        self.__GPSstopSending = True
    
    def __collectGPSData(self):
        self.__GPScollectData = True

    def ColData(self):
        self.__collectGPSData()

    def close(self):
        self.__disconnect()
        self.__logger.info('Serial connection to '+self.__port+' closed')
        self.__stopWorking()
    
    def __processData(self):
        if self.__serData != '':
            if self.__readRAW:
                self.__logger.debug('Received Raw Data: %s' % self.__serData)
                if self.__serData == 'OK\r\n':
                    self.__smsToBuild.Message = self.__smsToBuild.Message.rstrip('\r\n')
                    self.__smsList.append(self.__smsToBuild)
                    self.__readRAW = False
                    self.__writeLock = False
                else:
                    #self.__smsToBuild.Message = bytearray.fromhex(self.__serData).decode()
                    self.__smsToBuild.Message = self.__smsToBuild.Message + self.__serData
            else:
                self.__logger.debug('Received Data: %s' % self.__serData)

                if 'OK' in self.__serData:
                    self.__writeLock = False
                    self.__logger.debug('Lock Off')
                elif '+CME ERROR:' in self.__serData:
                    self.__writeLock = False

                    match = re.findall(self.regexGetSingleValue, self.__serData)
                    self.__cmeErr = int(match[0][1])

                    self.__logger.info('Got CME ERROR: %s' % match[0][1])
                elif '+CMS ERROR:' in self.__serData:
                    self.__writeLock = False

                    match = re.findall(self.regexGetSingleValue, self.__serData)
                    self.__cmsErr = int(match[0][1])

                    self.__logger.info('Got CMS ERROR: %s' % match[0][1])
                elif '+CPMS:' in self.__serData:
                    match = re.findall(self.regexGetAllValues, self.__serData)
                    rawData = match[0][1].split(',')
                    self.__masSMSSpace = int(rawData[1])
                    numSMS = int(rawData[0])
                    if numSMS > 0:
                        self.__smsToRead = 1
                    
                elif '+CMGR:' in self.__serData:
                    # read SMS content
                    match = re.findall(self.regexGetAllValues, self.__serData)
                    rawData = match[0][1].split('","')
                    self.__readRAW = True
                    self.__smsToBuild = SMS()
                    #self.__smsToBuild.Sender = bytearray.fromhex(rawData[1]).decode()
                    self.__smsToBuild.Sender = rawData[1]
                    self.__smsToBuild.Date = rawData[3].replace('"', '')
                    self.__smsToBuild.Date = datetime.strptime(rawData[3].replace('"', '')[:-3], '%y/%m/%d,%H:%M:%S')
                    self.__smsToBuild.Message = ''

                # unannounced data reception below (e.g. new SMS oder phone call)
                elif '+CMTI:' in self.__serData:
                    self.__logger.info('Received new SMS')
                    match = re.findall(self.regexGetAllValues, self.__serData)
                    rawData = match[0][1].split(',')
                    storage = rawData[0]
                    numSMS = int(rawData[1])
                    self.__logger.debug('New SMS in memory ' + storage + ' at position ' + str(numSMS))
                    self.__smsToRead = numSMS
                
                # GPS Data coming here
                elif '+CGNSINF:' in self.__serData:
                    self.__logger.debug('New GPS Data:')
                    match = re.findall(self.regexGetAllValues, self.__serData)
                    rawData = match[0][1].split(',')
                    
                    newGPS = GPS()

                    try:
                        newGPS.GNSS_status = int(rawData[0])
                    except:
                        pass
                    try:
                        newGPS.Fix_status = int(rawData[1])
                    except:
                        pass
                    try:
                        newGPS.UTC = datetime.strptime(rawData[2][:-4], '%Y%m%d%H%M%S')
                    except:
                        pass
                    try:
                        newGPS.Latitude = float(rawData[3])
                    except:
                        pass
                    try:
                        newGPS.Longitude = float(rawData[4])
                    except:
                        pass
                    try:
                        newGPS.Altitude = float(rawData[5])
                    except:
                        pass
                    try:
                        newGPS.Speed = float(rawData[6])
                    except:
                        pass
                    try:
                        newGPS.Course = float(rawData[7])
                    except:
                        pass
                    try:
                        newGPS.HDOP = float(rawData[10])
                    except:
                        pass
                    try:
                        newGPS.PDOP = float(rawData[11])
                    except:
                        pass
                    try:
                        newGPS.VDOP = float(rawData[12])
                    except:
                        pass
                    try:
                        newGPS.GPS_satellites = int(rawData[14])
                    except:
                        pass
                    try:
                        newGPS.GNSS_satellites = int(rawData[15])
                    except:
                        pass
                    try:
                        newGPS.Signal = float(rawData[18])/55.0
                    except:
                        pass

                    self.__GPSactualData = newGPS


            self.__serData = ''

    def __waitForUnlock(self):
        actTime = int(round(time.time()))
        if self.__sentTimeout > 0 and actTime > self.__sentTimeout:
            # Timeout
            self.__logger.error('Timeout during data reception')

            if self.__state == 2:
                # It might be that the gsm module is not powered on
                # So let's try
                self.__logger.error('Try to restart gsm module')
                self.__pressPowerKey()
                self.__state = 1
                self.__writeLock = False
                self.__sentTimeout = 0
                return False
            else:
                raise 'Unhandled timeout during data reception'

        if self.__writeLock:
            return False
        else:
            self.__sentTimeout = 0
            return True

    def __workerThread(self):
        self.__logger.info('Worker started')
        self.__waitTime = 0

        while self.__working:
            # Check for incoming chars
            while self.__ser.inWaiting() > 0:
                newChar = self.__ser.read().decode('iso-8859-1')

                if newChar == '\n':
                    if self.__readRAW == True:
                        self.__serData += newChar
                    self.__processData()
                else:
                    if newChar == '\r':
                        if self.__readRAW == True:
                            self.__serData += newChar
                    else:
                        self.__serData += newChar

            # Statemachine
            actTime = int(round(time.time() * 1000))
            if self.__state == 1:
                if self.__sendToHat('AT+CMGF=1'):
                    self.__startGPSUnit()
                    self.__stopGPSsending()
                    self.__state = 2
            elif self.__state == 2:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+CPMS="SM"'):
                        self.__state = 3
            elif self.__state == 3:
                if self.__waitForUnlock():
                    self.__state = 97
                    self.__nextState = 2
                    self.__waitTime = actTime + 5000
            elif self.__state == 20:
                # Read SMS
                if self.__sendToHat('AT+CMGR='+str(self.__smsToRead)):
                    self.__state = 21
            elif self.__state == 21:
                if self.__waitForUnlock():
                    if self.__smsToBuild == None:
                        # An der Stelle self.__smsToRead gab es keine SMS zu lesen
                        pass
                    else:
                        # Es gab eine neue SMS
                        self.__smsToBuild = None

                    # Lösche die behandelte SMS an der Stelle
                    if self.__sendToHat('AT+CMGD='+str(self.__smsToRead)):
                        self.__state = 22

            elif self.__state == 22:
                if self.__waitForUnlock():
                    if(self.__smsToRead == 20):
                        self.__smsToRead = 0
                    else:
                        self.__smsToRead = self.__smsToRead + 1

                    self.__state = 97
                    self.__nextState = 2
                    self.__waitTime = actTime + 5000
            
            elif self.__state == 30:
                # SMS versenden
                retSMS = self.__smsSendList[0]
                messageString = 'AT+CMGS="' + retSMS.Receiver + '"\n' + retSMS.Message + '\x1A'
                self.timeoutSerial = 30
                if self.__sendToHat(messageString):
                    self.__state = 31

            elif self.__state == 31:
                if self.__waitForUnlock():
                    retSMS = self.__smsSendList[0]
                    self.__logger.info('Message to ' + retSMS.Receiver + ' successfully sent')
                    del self.__smsSendList[0]
                    self.timeoutSerial = 5

                    self.__state = 97
                    self.__nextState = 2
                    self.__waitTime = actTime + 5000

            elif self.__state == 40:
                if self.__sendToHat('ATD' + self.__numberToCall + ';'):
                    self.__state = 41

            elif self.__state == 41:
                if self.__waitForUnlock():
                    self.__waitTime = actTime + self.__callTimeout * 1000
                    self.__state = 42

            elif self.__state == 42:
                    # Wait x Seconds
                if actTime > self.__waitTime or self.__sendHangUp == True:
                    self.__numberToCall = ''
                    self.__sendHangUp = True
                    self.__state = 97
                    self.__nextState = 2
                    self.__waitTime = actTime + 5000
            
            elif self.__state == 43:
                if self.__sendToHat('AT+CHUP'):
                    self.__state = 44

            elif self.__state == 44:
                if self.__waitForUnlock():
                    self.__sendHangUp = False
                    self.__state = 97
                    self.__nextState = 2
                    self.__waitTime = actTime + 5000

            elif self.__state == 50:
                if self.__sendToHat('AT+CGNSPWR=1'):
                    self.__state = 51

            elif self.__state == 51:
                if self.__waitForUnlock():
                    self.__logger.debug('GPS powered on')
                    self.__startGPS = False
                    self.__state = 97
                    self.__nextState = 2
                    self.__waitTime = actTime + 5000
                
            elif self.__state == 52:
                if self.__sendToHat('AT+CGNSTST=1'):
                    self.__state = 55
                    self.__logger.debug('GPS start sending')
                    self.__GPSstartSending = False

            elif self.__state == 53:
                if self.__sendToHat('AT+CGNSTST=0'):
                    self.__state = 55
                    self.__GPSstopSending = False

            elif self.__state == 54:
                if self.__sendToHat('AT+CGNSINF'):
                    self.__state = 55
                    self.__GPScollectData = False

            elif self.__state == 55:
                if self.__waitForUnlock():
                    self.__state = 97
                    self.__nextState = 2
                    self.__waitTime = actTime + 5000

            elif self.__state == 97:
                # Check if new SMS to send is there        
                if len(self.__smsSendList) > 0:
                    self.__state = 30
                
                # Check if we have to Call somebody
                elif self.__numberToCall != '':
                    self.__state = 40

                # Should I Hang Up ?
                elif self.__sendHangUp:
                    self.__state = 43

                # Check if new SMS is there
                elif self.__smsToRead > 0:
                    self.__state = 20

                # Check if GPS Unit should start
                elif self.__startGPS:
                    self.__state = 50

                # Check if GPS Unit should start send
                elif self.__GPSstartSending:
                    self.__state = 52

                # Check if GPS Unit should stop send
                elif self.__GPSstopSending:
                    self.__state = 53

                # Check if Single GPS Data should be collected
                elif self.__GPScollectData:
                    self.__state = 54

                elif actTime > self.__GPSwaittime:
                    self.__GPScollectData = True
                    self.__GPSwaittime = actTime + self.__GPStimeout

                # Wait x Seconds
                elif actTime > self.__waitTime:
                    self.__state = self.__nextState
            elif self.__state == 98:
                #Check if alive
                self.__logger.debug('Check if alive 98')
                if self.__sendToHat('AT'):
                    self.__state = 99
            elif self.__state == 99:
                #Check if alive
                if self.__waitForUnlock():
                    self.__state = 97
                    self.__nextState = 98
                    self.__waitTime = actTime + 5000

            # Let other Threads also do their job
            time.sleep(0.1)
        self.__logger.info('Worker ended')