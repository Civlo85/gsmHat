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
    regexGetAllValues = r'([+][a-zA-Z:\s]+)([\w\",\s+-\/:.]+)'
    timeoutSerial = 5
    timeoutGPSActive = 1
    timeoutGPSInactive = 2000
    cSMSwaittime = 2500             # milliseconds
    cGPRSstatusWaittime = 5000      # milliseconds

    def __init__(self, SerialPort, Baudrate, Logpath='gmsHat.log'):
        self.__baudrate = Baudrate
        self.__port = SerialPort

        self.__logger = logging.getLogger(__name__)
        self.__logger.setLevel(logging.DEBUG)
        self.__loggerFileHandle = logging.FileHandler(Logpath)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        self.__loggerFileHandle.setFormatter(formatter)
        self.__loggerFileHandle.setLevel(logging.DEBUG)
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
        self.__nextState = 0
        self.__smsToRead = 0
        self.__retryAfterTimeout = False
        self.__retryAfterTimeoutCount = 0
        self.__init = False
        self.__lastCommandSentString = ''
        self.__readRAW = 0
        self.__smsToBuild = None
        self.__smsList = []
        self.__smsSendList = []
        self.__SMSwaittime = 0
        self.__numberToCall = ''
        self.__sendHangUp = False
        self.__startGPS = False
        self.__GPRSwaittimeStatus = 0
        self.__GPRSIPaddress = ''
        self.__GPRSready = False
        self.__GPRSuserAPN = None
        self.__GPRSuserUSER = None
        self.__GPRSuserPWD = None
        self.__GPRScallUrlList = []
        self.__GPRSdataReceived = []
        self.__GPRSwaitForData = False
        self.__GPSstarted = False
        self.__GPSstartSending = False
        self.__GPSstopSending = False
        self.__GPScollectData = False
        self.__GPSactualData = GPS()
        self.__GPStimeout = self.timeoutGPSInactive
        self.__GPSwaittime = 0
        self.__workerThread = threading.Thread(target=self.__workerThread, daemon=True)
        self.__workerThread.start()

    def __stopWorking(self):
        self.__working = False
        self.__workerThread.join(10.0)  # Timeout = 10.0 Seconds

    def __sendToHat(self, string):
        if self.__writeLock == False:
            self.__lastCommandSentString = string
            string = string + '\n'
            self.__ser.write(string.encode('iso-8859-1'))
            self.__writeLock = True
            self.__sentTimeout = int(round(time.time())) + self.timeoutSerial
            self.__logger.debug('Sent to hat: %s' % string)
            return True
        else:
            self.__logger.debug('Wait for Lock...   state: ' + str(self.__state) + ' senddata: ' + string)
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

    def UrlResponse_available(self):
        return len(self.__GPRSdataReceived)

    def UrlResponse_read(self):
        if self.UrlResponse_available() > 0:
            retResponse = self.__GPRSdataReceived[0]
            del self.__GPRSdataReceived[0]
            return retResponse

        return None

    def CallUrl(self, url):
        self.__GPRScallUrlList.append(url)
        self.__logger.debug('Got new URL call')

    def PendingUrlCalls(self):
        return len(self.__GPRScallUrlList)

    def SetGPRSconnection(self, APN, Username, Password):
        self.__GPRSuserAPN = APN
        self.__GPRSuserUSER = Username
        self.__GPRSuserPWD = Password

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
            if self.__readRAW > 0:
                self.__logger.debug('Received Raw Data: %s' % self.__serData)
                if self.__readRAW == 1:
                    # Handle SMS
                    if self.__serData == 'OK\r\n':
                        self.__smsToBuild.Message = self.__smsToBuild.Message.rstrip('\r\n')
                        self.__smsList.append(self.__smsToBuild)
                        self.__readRAW = 0
                        self.__writeLock = False
                    else:
                        self.__smsToBuild.Message = self.__smsToBuild.Message + self.__serData
                elif self.__readRAW == 2:
                    # Handle HTTP Response
                    if self.__serData == 'OK\r\n':
                        self.__readRAW = 0
                        self.__writeLock = False
                        self.__GPRSdataToBuild = self.__GPRSdataToBuild.rstrip('\r\n')
                        self.__GPRSdataReceived.append(self.__GPRSdataToBuild)
                    else:
                        self.__GPRSdataToBuild = self.__GPRSdataToBuild + self.__serData
            else:
                self.__logger.debug('Received Data: %s' % self.__serData)

                if 'OK' in self.__serData:
                    self.__writeLock = False
                    self.__logger.debug('Lock Off')
                if 'ERROR' in self.__serData:
                    # ERROR Handling here
                    if self.__state == 71:
                        # Error after sending AT+HTTPINIT
                        # Lets terminate request before starting new one
                        self.__logger.info('Error after starting new HTTP Request.')
                        self.__writeLock = False
                        self.__state = 75
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
                    self.__readRAW = 1
                    self.__smsToBuild = SMS()
                    #self.__smsToBuild.Sender = bytearray.fromhex(rawData[1]).decode()
                    self.__smsToBuild.Sender = rawData[1]
                    self.__smsToBuild.Date = rawData[3].replace('"', '')
                    self.__smsToBuild.Date = datetime.strptime(rawData[3].replace('"', '')[:-3], '%y/%m/%d,%H:%M:%S')
                    self.__smsToBuild.Message = ''

                elif '+SAPBR:' in self.__serData:
                    # check if IP is valid
                    # Return value looks like: +SAPBR: 1,3,"0.0.0.0"
                    match = re.findall(self.regexGetAllValues, self.__serData)
                    rawData = match[0][1].split(',')
                    self.__GPRSIPaddress = rawData[2].replace('"', '')

                    if self.__GPRSIPaddress != '0.0.0.0':
                        self.__GPRSready = True
                    else:
                        self.__GPRSready = False

                elif '+HTTPREAD:' in self.__serData:
                    # read HTTP content
                    self.__GPRSdataToBuild = ''
                    self.__readRAW = 2

                elif '+HTTPACTION:' in self.__serData:
                    # Return value looks like: +HTTPACTION: 0,200,0
                    match = re.findall(self.regexGetAllValues, self.__serData)
                    rawData = match[0][1].split(',')
                    self.__GPRSgotHttpResponse = True
                    if len(rawData) == 3:
                        requestMethod = int(rawData[0])
                        httpStatus = int(rawData[1])
                        recvDataLength = int(rawData[2])
                        if httpStatus == 200:  # Successful request
                            self.__GPRSnewDataReceived = True
                        elif httpStatus == 601:  # Successful request
                            self.__logger.info('HTTPACTION Network Error ' + str(httpStatus))
                        else:
                            self.__logger.info('HTTPACTION Unhandled Error ' + str(httpStatus))

                    else:
                        self.__logger.info('HTTPACTION return value is not expected: ' + match[0][1])

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
                    if len(rawData) == 21:                    
                        newGPS = GPS()
                        goodPosition = True

                        try:
                            newGPS.GNSS_status = int(rawData[0])
                        except:
                            self.__logger.debug('GNSS_status: Could not convert ' + rawData[0] + ' to int.')

                        try:
                            # Fix_status: GPS connection
                            newGPS.Fix_status = int(rawData[1])
                            if newGPS.Fix_status == 0:
                                goodPosition = False
                        except:
                            self.__logger.debug('Fix_status: Could not convert ' + rawData[1] + ' to int.')

                        try:
                            newGPS.UTC = datetime.strptime(rawData[2][:-4], '%Y%m%d%H%M%S')
                        except:
                            self.__logger.debug('UTC: Could not convert ' + rawData[2][:-4] + ' to int.')

                        try:
                            newGPS.Latitude = float(rawData[3])
                            if newGPS.Latitude == 0.0:
                                goodPosition = False
                        except:
                            self.__logger.debug('Latitude: Could not convert ' + rawData[3] + ' to float.')

                        try:
                            newGPS.Longitude = float(rawData[4])
                            if newGPS.Longitude == 0.0:
                                goodPosition = False
                        except:
                            self.__logger.debug('Longitude: Could not convert ' + rawData[4] + ' to float.')

                        try:
                            newGPS.Altitude = float(rawData[5])
                            if newGPS.Altitude == 0.0:
                                goodPosition = False
                        except:
                            self.__logger.debug('Altitude: Could not convert ' + rawData[5] + ' to float.')

                        try:
                            newGPS.Speed = float(rawData[6])
                        except:
                            self.__logger.debug('Speed: Could not convert ' + rawData[6] + ' to float.')

                        try:
                            newGPS.Course = float(rawData[7])
                        except:
                            self.__logger.debug('Course: Could not convert ' + rawData[7] + ' to float.')

                        try:
                            newGPS.HDOP = float(rawData[10])
                        except:
                            self.__logger.debug('HDOP: Could not convert ' + rawData[10] + ' to float.')

                        try:
                            newGPS.PDOP = float(rawData[11])
                            if newGPS.PDOP == 0.0:
                                goodPosition = False
                        except:
                            self.__logger.debug('PDOP: Could not convert ' + rawData[11] + ' to float.')

                        try:
                            newGPS.VDOP = float(rawData[12])
                        except:
                            self.__logger.debug('VDOP: Could not convert ' + rawData[12] + ' to float.')

                        try:
                            newGPS.GPS_satellites = int(rawData[14])
                        except:
                            self.__logger.debug('GPS_satellites: Could not convert ' + rawData[14] + ' to int.')

                        try:
                            newGPS.GNSS_satellites = int(rawData[15])
                        except:
                            self.__logger.debug('GNSS_satellites: Could not convert ' + rawData[15] + ' to int.')

                        try:
                            newGPS.Signal = float(rawData[18])/55.0
                        except:
                            self.__logger.debug('Signal: Could not convert ' + rawData[18] + ' to float.')
                        
                        if goodPosition:
                            self.__GPSactualData = newGPS


            self.__serData = ''

    def __restartProcedure(self):
        self.__logger.error('Try to restart gsm module')
        self.__pressPowerKey()
        self.__state = 1
        self.__writeLock = False
        self.__retryAfterTimeout = False
        self.__sentTimeout = 0

    def __waitForUnlock(self):
        actTime = int(round(time.time()))
        if self.__sentTimeout > 0 and actTime > self.__sentTimeout:
            # Timeout
            self.__logger.error('Timeout during data reception')
            self.__logger.info('Command sent: ' + self.__lastCommandSentString)
            self.__logger.info('Actual state of programme: ' + str(self.__state))

            if self.__state == 2 or self.__state == 97:
                # It might be that the gsm module is not powered on
                # So let's try to restart
                self.__restartProcedure()
                return False
            elif  self.__state == 3:
                # Tried to check for new SMS
                # Retry 3 times
                if self.__retryAfterTimeout:
                    if self.__retryAfterTimeoutCount > 0:
                        self.__retryAfterTimeoutCount -= 1
                    else:
                        self.__restartProcedure()
                        return False
                else:
                    self.__retryAfterTimeout = True
                    self.__retryAfterTimeoutCount = 3

                self.__state = 2
                self.__writeLock = False
                self.__sentTimeout = 0
                return False
            else:
                self.__logger.critical('Exception: Unhandled timeout during data reception')
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
                    if self.__readRAW > 0:
                        self.__serData += newChar
                    self.__processData()
                else:
                    if newChar == '\r':
                        if self.__readRAW > 0:
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
                        self.__logger.info('New Message from ' + self.__smsToBuild.Sender + ' was received')
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
            
            elif self.__state == 43:
                if self.__sendToHat('AT+CHUP'):
                    self.__state = 44

            elif self.__state == 44:
                if self.__waitForUnlock():
                    self.__sendHangUp = False
                    self.__state = 97

            elif self.__state == 50:
                if self.__sendToHat('AT+CGNSPWR=1'):
                    self.__state = 51

            elif self.__state == 51:
                if self.__waitForUnlock():
                    self.__logger.debug('GPS powered on')
                    self.__startGPS = False
                    self.__state = 97
                
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
            
            elif self.__state == 60:
                if self.__sendToHat('AT+SAPBR=2,1'):
                    self.__state = 61

            elif self.__state == 61:
                if self.__waitForUnlock():
                    tempState = 97
                    if self.__GPRSready == True:
                        pass
                    else:
                        if self.__GPRSuserAPN != None and self.__GPRSuserUSER != None and self.__GPRSuserPWD != None:
                            # try to connect
                            tempState = 62

                    self.__state = tempState

            elif self.__state == 62:
                if self.__sendToHat('AT+SAPBR=3,1,"Contype","GPRS"'):
                    self.__state = self.__state + 1

            elif self.__state == 63:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+SAPBR=3,1,"APN","' + self.__GPRSuserAPN + '"'):
                        self.__state = self.__state + 1
            
            elif self.__state == 64:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+SAPBR=3,1,"USER","' + self.__GPRSuserUSER + '"'):
                        self.__state = self.__state + 1
            
            elif self.__state == 65:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+SAPBR=3,1,"PWD","' + self.__GPRSuserPWD + '"'):
                        self.__state = self.__state + 1
            
            elif self.__state == 66:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+SAPBR=1,1'):
                        self.__state = self.__state + 1
            
            elif self.__state == 67:
                if self.__waitForUnlock():
                    self.__state = 97

            elif self.__state == 70:
                # Call the first URL in List
                if self.__sendToHat('AT+HTTPINIT'):
                    self.__state = self.__state + 1

            elif self.__state == 71:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+HTTPPARA="CID",1'):
                        self.__state = self.__state + 1

            elif self.__state == 72:
                if self.__waitForUnlock():
                    getUrl = self.__GPRScallUrlList[0]
                    if self.__sendToHat('AT+HTTPPARA="URL","' + getUrl + '"'):
                        del self.__GPRScallUrlList[0]
                        self.__GPRSwaitForData = True
                        self.__GPRSnewDataReceived = False
                        self.__GPRSgotHttpResponse = False
                        self.__state = self.__state + 1
            
            elif self.__state == 73:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+HTTPACTION=0'):
                        self.__state = 97
                        #self.__state = self.__state + 1
            
            elif self.__state == 74:
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+HTTPREAD'):
                        self.__state = self.__state + 1
            
            elif self.__state == 75:
                # Close HTTP Request
                if self.__waitForUnlock():
                    if self.__sendToHat('AT+HTTPTERM'):
                        self.__state = 97
                        self.__GPRSwaitForData = False
                        self.__GPRSnewDataReceived = False

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

                # Check if we should call some Urls
                elif len(self.__GPRScallUrlList) > 0 and self.__GPRSready and self.__GPRSwaitForData == False:
                    self.__state = 70
                
                elif self.__GPRSwaitForData and self.__GPRSgotHttpResponse:
                    if self.__GPRSnewDataReceived:
                        self.__state = 74
                    else:
                        self.__state = 75

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
                
                elif actTime > self.__SMSwaittime:
                    self.__state = 2
                    self.__SMSwaittime = actTime + self.cSMSwaittime
                
                elif actTime > self.__GPRSwaittimeStatus:
                    self.__state = 60
                    self.__GPRSwaittimeStatus = actTime + self.cGPRSstatusWaittime

                # Wait x Seconds
                elif actTime > self.__waitTime:
                    if self.__nextState > 0:
                        self.__state = self.__nextState
                        self.__nextState = 0
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