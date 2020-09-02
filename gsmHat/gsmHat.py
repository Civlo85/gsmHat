#!/usr/bin/python3
# Filename: gsmHat.py
import logging
import serial
import threading
import time
import re
from datetime import datetime
import RPi.GPIO as GPIO

class SMS:
    def __init__(self):
        self.Message = ''
        self.Sender = ''
        self.Receiver = ''
        self.Date = ''

class GSMHat:
    """GSM Hat Backend with SMS Functionality (for now)"""
    
    regexGetSingleValue = r'([+][a-zA-Z\ ]+(:\ ))([\d]+)'
    regexGetAllValues = r'([+][a-zA-Z:\s]+)([\w\",\s+\/:]+)'
    timeoutSerial = 5

    def __init__(self, SerialPort, Baudrate):
        self.__baudrate = Baudrate
        self.__port = SerialPort

        self.__logger = logging.getLogger(__name__)
        self.__logger.setLevel(logging.DEBUG)
        self.__loggerFileHandle = logging.FileHandler('gsmHat.log')
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
        self.__smsToRead = 0
        self.__init = False
        self.__readRAW = False
        self.__smsToBuild = None
        self.__smsList = []
        self.__smsSendList = []
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

            elif self.__state == 97:
                # Check if new SMS to send is there        
                if len(self.__smsSendList) > 0:
                    self.__state = 30

                # Check if new SMS is there
                elif self.__smsToRead > 0:
                    self.__state = 20

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