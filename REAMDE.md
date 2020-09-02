# gsmHat - Waveshare GSM/GPRS/GNSS HAT for Raspberry Pi with Python

With gsmHat, you can easily use the functionality of the Waveshare GSM/GPRS/GNSS HAT for Raspberry Pi ([Link to HAT](https://www.waveshare.com/gsm-gprs-gnss-hat.htm)). On this module a SIM868 Controller is doing the job too connect your Raspberry Pi with the world just by using a sim card.

## Overview
gsmHat was written for Python 3. It provides the following features

  - Non-blocking receiving and sending SMS in background

## Usage

In the following paragraphs, I am going to describe how you can get and use gsmHat for your own projects.

###  Getting it

To download scrapeasy, either fork this github repo or simply use Pypi via pip.
```sh
$ pip3 install gsmHat
```

### Prepare

* Install your sim card in your module, connect the GSM antenna and mount the module on the pin headers of your Raspberry Pi
  Make sure, that you **do not** need to enter Pin Code to use your card

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
from gsmHat import GSMHat, SMS
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
## What will come in the future?

* Outgoing and Incoming Calls
* GPS functionality
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
