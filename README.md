# gsmHat - Waveshare GSM/GPRS/GNSS HAT for Raspberry Pi with Python

With gsmHat, you can easily use the functionality of the Waveshare GSM/GPRS/GNSS HAT for Raspberry Pi ([Link to HAT](https://www.waveshare.com/gsm-gprs-gnss-hat.htm)). On this module a SIM868 Controller is doing the job to connect your Raspberry Pi with the world just by using a sim card.

## Update on Wed Oct 21st, 2020
:point_right: Internet functionality added!

## Overview
gsmHat was written for Python 3. It provides the following features

  - Non-blocking receiving and sending SMS in background
  - Non-blocking calling
  - Non-blocking refreshing of actual gps position
  - Non-blocking URL Call and receiving of response

## Usage

In the following paragraphs, I am going to describe how you can get and use gsmHat for your own projects.

###  Getting it

To download gsmHat, either fork this github repo or simply use Pypi via pip.
```sh
$ pip3 install gsmHat
```

### Prepare

* Install your sim card in your module, connect the GSM and the GPS antennas and mount the module on the pin headers of your Raspberry Pi. Make sure, that you **do not** need to enter Pin Code to use your card. Pin Codes are not supported yet.

* Enable the Uart Interface in your Raspberry Pi

    1. Start raspi-config: `sudo raspi-config`.
    2. Select option 5 - interfacing options.
    3. Select option P6 - serial.
    4. At the prompt `Would you like a login shell to be accessible over serial?` answer 'No'
    5. At the prompt `Would you like the serial port hardware to be enabled?` answer 'Yes'
    6. Exit raspi-config and reboot the Pi for changes to take effect.

### Using it

1. Import gsmHat to your project

```Python
from gsmHat import GSMHat, SMS, GPS
```

2. Init gsmHat

```Python
gsm = GSMHat('/dev/ttyS0', 115200)
```

3. Check, if new SMS are available in your main loop

```Python
# Check, if new SMS is available
if gsm.SMS_available() > 0:
    # Get new SMS
    newSMS = gsm.SMS_read()
    # Do something with it
```

4. Do something with your newly received SMS

```Python
# Get new SMS
newSMS = gsm.SMS_read()

print('Got new SMS from number %s' % newSMS.Sender)
print('It was received at %s' % newSMS.Date)
print('The message is: %s' % newSMS.Message)
```

5. You can also write SMS

```Python
Number = '+491601234567'
Message = 'Hello mobile world'

# Send SMS
gsm.SMS_write(Number, Message)
```

6. Or you can call a number

```Python
Number = '+491601234567'
gsm.Call(Number)        # This call hangs up automatically after 15 seconds
time.sleep(10)          # Wait 10 seconds ...
gsm.HangUp()            # Or you can HangUp by yourself earlier
gsm.Call(Number, 60)    # Or lets change the timeout to 60 seconds. This call hangs up automatically after 60 seconds
```

7. Lets see, where your Raspberry Pi (in a car or on a motocycle or on a cat?) is positioned on earth

```Python
# Get actual GPS position
GPSObj = gsm.GetActualGPS()

# Lets print some values
print('GNSS_status: %s' % str(GPSObj.GNSS_status))
print('Fix_status: %s' % str(GPSObj.Fix_status))
print('UTC: %s' % str(GPSObj.UTC))
print('Latitude: %s' % str(GPSObj.Latitude))
print('Longitude: %s' % str(GPSObj.Longitude))
print('Altitude: %s' % str(GPSObj.Altitude))
print('Speed: %s' % str(GPSObj.Speed))
print('Course: %s' % str(GPSObj.Course))
print('HDOP: %s' % str(GPSObj.HDOP))
print('PDOP: %s' % str(GPSObj.PDOP))
print('VDOP: %s' % str(GPSObj.VDOP))
print('GPS_satellites: %s' % str(GPSObj.GPS_satellites))
print('GNSS_satellites: %s' % str(GPSObj.GNSS_satellites))
print('Signal: %s' % str(GPSObj.Signal))
```

8. Calculate the distance between two Points on earth

```Python
GPSObj1 = GPS()                 # You can also use gsm.GetActualGPS() to get an GPS object
GPSObj1.Latitude = 52.266949    # Location of Braunschweig, Germany
GPSObj1.Longitude = 10.524822

GPSObj2 = GPS()
GPSObj2.Latitude = 36.720005    # Location of Manavgat, Turkey
GPSObj2.Longitude = 31.546094

print('Distance from Braunschweig to Manavgat in metres:')
print(GPS.CalculateDeltaP(GPSObj1, GPSObj2))        # this will print 2384660.7 metres
```

9. Call URL to send some data

```Python
# Init gsmHat
gsm = GSMHat('/dev/ttyS0', 115200)

# Set the APN Connection data. You will get this from your provider
# e.g. German Provider 'Congstar'
gsm.SetGPRSconnection('internet.telekom', 'congstar', 'cs')

# Get actual GPS position
GPSObj = gsm.GetActualGPS()

# Build url string with data
url = 'www.someserver.de/myscript.php'
url += '?time='+str(int(GPSObj.UTC.timestamp()))
url += '&lat='+str(GPSObj.Latitude)
url += '&lon='+str(GPSObj.Longitude)
url += '&alt='+str(GPSObj.Altitude)

gsm.CallUrl(url)    # Send actual position to a webserver
```

10. Get the Response from a previous URL call

```Python
# Check, if new Response Data is available
if gsm.UrlResponse_available() > 0:
    # Read the Response
    newResponse = gsm.UrlResponse_read()
    # Do something with it
```

## What will come in the future?

* More options to configure the module (e.g. using sim cards with pin code)

## On which platform was gsmHat developed and tested?

### Hardware:
* [Raspberry Pi 4, Model B](https://www.raspberrypi.org/products/raspberry-pi-4-model-b/)
* [GSM/GPRS/GNSS/Bluetooth HAT for Raspberry Pi](https://www.waveshare.com/gsm-gprs-gnss-hat.htm), **later version that allows to power on/off the module by controlling GPIO 4**

### Software:
* Raspbian (Codename: buster, Release: 10)
* Kernel: Linux 5.4.51-v7l+
* Python: 3.7.3


License
----

MIT License

Copyright (c) 2020 Tarek Tounsi

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.


contact me: <software@tounsi.de>