#!/usr/bin/env python
# -*- coding: utf-8 -*-

# pylint: disable=line-too-long

import time
from datetime import datetime
import subprocess
import sys
import RPi.GPIO as GPIO
import redis
import paho.mqtt.client as mqtt
import socket
import fcntl
import struct
import logging
import logging.handlers
import atexit
import os
from select import select

# Local files
import lcddriver
import gsmhuaweistatus

# ------------------------------------------------------------------------------------
# Script version
version = '2.1.0'
# ------------------------------------------------------------------------------------

# ------------------------------------------------------------------------------------
# emonPi Node ID (default 5)
# ------------------------------------------------------------------------------------
emonPi_nodeID = 5

# ------------------------------------------------------------------------------------
# MQTT Settings
# ------------------------------------------------------------------------------------
mqtt_user = "emonpi"
mqtt_passwd = "emonpimqtt2016"
mqtt_host = "127.0.0.1"
mqtt_port = 1883
mqtt_topic = "emonhub/rx/" + str(emonPi_nodeID) + "/values"

# ------------------------------------------------------------------------------------
# Redis Settings
# ------------------------------------------------------------------------------------
redis_host = 'localhost'
redis_port = 6379

# ------------------------------------------------------------------------------------
# Huawei Hi-Link GSM/3G USB dongle IP address on eth1
# ------------------------------------------------------------------------------------
hilink_device_ip = '192.168.1.1'

# ------------------------------------------------------------------------------------
# I2C LCD: each I2C address will be tried in consecutive order until LCD is found
# The first address that matches a device on the I2C bus will be used for the I2C LCD
# ------------------------------------------------------------------------------------
#lcd_i2c = ['20', '21', '22', '23', '24', '25', '26', '27']  #PCF8574T default address is 0x27
lcd_i2c = ['38', '39', '3a', '3b', '3c', '3d', '3e', '3f']  #PCF8574AT default address is 0x3f
current_lcd_i2c = ''

# LCD backlight timeout in seconds
# 0: always on, 300: off after 5 min
backlight_timeout = 300

# ------------------------------------------------------------------------------------

# Default Startup Page
max_number_pages = 8

# ------------------------------------------------------------------------------------
# Start Logging
# ------------------------------------------------------------------------------------
uselogfile = True


class IPAddress(object):
    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def get_ip_address(self, ifname):
        try:
            return socket.inet_ntoa(fcntl.ioctl(
                self.sock.fileno(),
                0x8915,  # SIOCGIFADDR
                struct.pack('256s', ifname[:15])
            )[20:24])
        except Exception:
            return 0


def shutdown(lcd):
    lcd.backlight = 1
    lcd[0] = "emonPi Shutdown"
    for x in range(1, 6):
        lcd[1] = ''.join(str(y) + '..' for y in range(5, 5-x, -1))
        time.sleep(1)

        if GPIO.input(11) == 0:
            return
    lcd[1] = "SHUTDOWN NOW!"
    time.sleep(2)
    lcd.lcd_clear()
    lcd[0] = "Wait 30s..."
    lcd[1] = "Before Unplug!"
    time.sleep(4)
    # backlight zero must be the last call to the LCD to keep the backlight off
    lcd.backlight = 0
    #subprocess.call('halt', shell=False)
    subprocess.call('poweroff', shell=False)
    sys.exit(0)  # end script


class LCD(object):
    def __init__(self, logger):
        # Scan I2C bus for LCD I2C addresses as defined in led_i2c, we have few models of LCD which have different addresses that are shipped with emonPi
        # First I2C device to match address is used
        self.logger = logger
        for i2c_address in lcd_i2c:
          lcd_status = subprocess.check_output(["/home/pi/emonpi/lcd/emonPiLCD_detect.sh", "%s" % i2c_address])
          if lcd_status.rstrip() == 'True':
            print "I2C LCD DETECTED  on Ox%s" % i2c_address
            logger.info("I2C LCD DETECTED 0x%s" % i2c_address)
            current_lcd_i2c = "0x%s" % i2c_address
            break
        
        if lcd_status.rstrip() == 'False':
          print ("I2C LCD NOT DETECTED on either 0x" + str(lcd_i2c) + " ...exiting LCD script")
          logger.error("I2C LCD NOT DETECTED on either 0x" + str(lcd_i2c) + " ...exiting LCD script")
          sys.exit(1)
        
        # Init LCD using detected I2C address with 16 characters
        self.lcd = lcddriver.lcd(int(current_lcd_i2c, 16))
        self._display = ['', '']

    def __setitem__(self, line, string):
        if not 0 <= line <= 1:
            raise IndexError("line number out of range")
        # Format string to exactly the width of LCD
        string = '{0!s:<16.16}'.format(string)
        if string != self._display[line]:
            self._display[line] = string
            self.logger.debug("LCD line {0}: {1}".format(line, string))
            self.lcd.lcd_display_string(string, line + 1)

    @property
    def backlight(self):
        return self.lcd.backlight

    @backlight.setter
    def backlight(self, state):
        if not 0 <= state <= 1:
            raise IndexError("backlight state out of range")
        self.logger.debug("LCD backlight: " + repr(state))
        self.lcd.backlight = state

    def lcd_clear(self):
        self.lcd.lcd_clear()


class ButtonInput(object):
    def __init__(self, logger, fd):
        GPIO.add_event_detect(16, GPIO.RISING, callback=self.buttonPress, bouncetime=1000)
        self.logger = logger
        self.press_num = 0
        self.pressed = False
        self.fd = fd

    def buttonPress(self, channel):
        self.pressed = True
        self.logger.info("lcd button press " + str(self.press_num))
        self.fd.write('1')


def main():
    # First set up logging
    atexit.register(logging.shutdown)
    if not uselogfile:
        loghandler = logging.StreamHandler()
    else:
        logfile = "/var/log/emonpilcd/emonpilcd.log"
        print "emonPiLCD logging to: "+logfile
        loghandler = logging.handlers.RotatingFileHandler(logfile,
                                                          mode='a',
                                                          maxBytes=1000 * 1024,
                                                          backupCount=1,
                                                         )

    loghandler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger = logging.getLogger("emonPiLCD")
    logger.addHandler(loghandler)
    logger.setLevel(logging.INFO)

    logger.info("Starting emonPiLCD V" + version)

    # Now check the LCD and initialise the object
    lcd = LCD(logger)
    lcd.backlight = 1

    # ------------------------------------------------------------------------------------
    # Discover & display emonPi SD card image version
    # ------------------------------------------------------------------------------------

    sd_image_version = ''
    sd_card_image = subprocess.call("ls /boot | grep emonSD", shell=True)
    if not sd_card_image:  # if emonSD file exists
        sd_image_version = subprocess.check_output("ls /boot | grep emonSD", shell=True)
    else:
        sd_card_image = subprocess.call("ls /boot | grep emonpi", shell=True)
        if not sd_card_image:
            sd_image_version = subprocess.check_output("ls /boot | grep emonpi", shell=True)
        else:
            sd_image_version = "N/A "
    sd_image_version = sd_image_version.rstrip()

    lcd[0] = "emonPi Build:"
    lcd[1] = sd_image_version
    logger.info("SD card image build version: " + sd_image_version)

    #Get CPU temperature using 'vcgencmd measure_temp'
    cpu_temp = ""
    cpu_t = os.popen('vcgencmd measure_temp').readline()
    cpu_temp = (cpu_t.replace("temp=","").replace("'C\n","\337C"))
    print cpu_temp

    # Set up the buttons and install handlers
    atexit.register(GPIO.cleanup)
    # Use Pi board pin numbers as these as always consistent between revisions
    GPIO.setmode(GPIO.BOARD)
    # emonPi LCD push button Pin 16 GPIO 23
    GPIO.setup(16, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    # emonPi Shutdown button, Pin 11 GPIO 17
    GPIO.setup(11, GPIO.IN)

    # Create a pipe with no buffering, make the read end non-blocking and pass
    # the other to the ButtonInput class
    pipe = os.pipe()
    pipe = (os.fdopen(pipe[0], 'r', 0), os.fdopen(pipe[1], 'w', 0))
    fcntl.fcntl(pipe[0], fcntl.F_SETFL, os.O_NONBLOCK)
    buttoninput = ButtonInput(logger, pipe[1])

    logger.info("Connecting to redis server...")

    r = redis.Redis(host=redis_host, port=redis_port, db=0)

    # We wait here until redis has successfully started up
    while True:
        try:
            r.client_list()
            break
        except redis.ConnectionError:
            logger.error("waiting for redis-server to start...")
            time.sleep(1.0)
    logger.info("Connected to redis")

    logger.info("Connecting to MQTT Server: " + mqtt_host + " on port: " + str(mqtt_port) + " with user: " + mqtt_user)
    def on_message(client, userdata, msg):
        topic_parts = msg.topic.split("/")
        if int(topic_parts[2]) == emonPi_nodeID:
            r.set("basedata", msg.payload)

    def on_connect(client, userdata, flags, rc):
        mqttc.subscribe(mqtt_topic)

    mqttc = mqtt.Client()
    mqttc.on_message = on_message
    mqttc.on_connect = on_connect

    try:
        mqttc.username_pw_set(mqtt_user, mqtt_passwd)
        mqttc.connect(mqtt_host, mqtt_port, 60)
        # Run MQTT background thread which handles reconnects
        mqttc.loop_start()
    except Exception:
        logger.error("Could not connect to MQTT")
    else:
        logger.info("Connected to MQTT")

    # time to show Build version
    time.sleep(2)

    buttonPress_time = time.time()
    page = 0

    # Create object for getting IP addresses of interfaces
    ipaddress = IPAddress()

    # Enter main loop
    while True:
        now = time.time()

        # turn backight off after backlight_timeout seconds
        if now - buttonPress_time > backlight_timeout and lcd.backlight:
            lcd.backlight = 0

        if buttoninput.pressed:
            buttoninput.pressed = False
            if lcd.backlight:
                page += 1
            if page > max_number_pages:
                page = 0
            buttonPress_time = now
            if not lcd.backlight:
                lcd.backlight = 1
            logger.info("Mode button pressed")
            logger.info("Page: " + str(page))

        # Get system parameters and store in redis
        # Get uptime
        with open('/proc/uptime', 'r') as f:
            seconds = float(f.readline().split()[0])
            r.set('uptime', seconds)

        # Update ethernet
        eth0ip = ipaddress.get_ip_address('eth0')
        r.set("eth:active", bool(eth0ip))
        r.set("eth:ip", eth0ip)

        # Update wifi
        wlan0ip = ipaddress.get_ip_address('wlan0')

        r.set("wlan:active", bool(wlan0ip))
        r.set("wlan:ip", wlan0ip)

        signallevel = 0
        if wlan0ip:
            # wlan link status
            with open('/proc/net/wireless', 'r') as f:
                wireless = f.readlines()
            signals = [x.split()[3] for x in wireless if x.strip().startswith('wlan0')]
            if signals:
                signallevel = signals[0].partition('.')[0]
                if signallevel.startswith('-'): # Detect the alternate signal strength reporting via dBm
                    signallevel = 2 * ( int(signallevel) + 100 ) # Convert to percent
        r.set("wlan:signallevel", signallevel)

        # Update Hi-Link 3G Dongle - connects on eth1
        if ipaddress.get_ip_address("eth1") and gsmhuaweistatus.is_hilink(hilink_device_ip):
            gsm_connection_status = gsmhuaweistatus.return_gsm_connection_status(hilink_device_ip)
            r.set("gsm:connection", gsm_connection_status[0])
            r.set("gsm:signal", gsm_connection_status[1])
            r.set("gsm:active", 1)
        else:
            r.set("gsm:active", 0)

        # Now display the appropriate LCD page
        if page == 0:
            if eval(r.get("eth:active")):
                lcd[0] = "Ethernet: YES"
                lcd[1] = r.get("eth:ip")
            elif eval(r.get("wlan:active")) or eval(r.get("gsm:active")):
                page += 1
            else:
                lcd[0] = "Ethernet:"
                lcd[1] = "NOT CONNECTED"

        if page == 1:
            if eval(r.get("wlan:active")):
                lcd[0] = "WIFI: YES  " + r.get("wlan:signallevel") + "%"
                lcd[1] = r.get("wlan:ip")
            elif eval(r.get("gsm:active")) or eval(r.get("eth:active")):
                page += 1
            else:
                lcd[0] = "WIFI:"
                lcd[1] = "NOT CONNECTED"

        if page == 2:
            if eval(r.get("gsm:active")):
                lcd[0] = r.get("gsm:connection")
                lcd[1] = r.get("gsm:signal")
            elif eval(r.get("eth:active")) or eval(r.get("wlan:active")):
                page += 1
            else:
                lcd[0] = "GSM:"
                lcd[1] = "NO DEVICE"

        if page == 3:
            basedata = r.get("basedata")
            if basedata is not None:
                basedata = basedata.split(",")
                lcd[0] = 'Power 1: ' + basedata[0] + "W"
                lcd[1] = 'Power 2: ' + basedata[1] + "W"
            else:
                lcd[0] = 'ERROR: MQTT'
                lcd[1] = 'Not connected'

        elif page == 4:
            basedata = r.get("basedata")
            if basedata is not None:
                basedata = basedata.split(",")
                lcd[0] = 'VRMS: ' + basedata[3] + "V"
                lcd[1] = 'Temp 1: ' + basedata[4] + "\337C"
            else:
                lcd[0] = 'ERROR: MQTT'
                lcd[1] = 'Not connected'

        elif page == 5:
            basedata = r.get("basedata")
            if basedata is not None:
                basedata = basedata.split(",")
                lcd[0] = 'Temp 2: ' + basedata[5] + "\337C"
                lcd[1] = 'Pulse: ' + basedata[10] + "p"
            else:
                lcd[0] = 'ERROR: MQTT'
                lcd[1] = 'Not connected'

        elif page == 6:
            lcd[0] = datetime.now().strftime('%b %d %H:%M')
            lcd[1] = 'Uptime %.2f days' % (seconds / 86400)

        elif page == 7:
            lcd[0] = 'CPU temp: '
            lcd[1] = '>>> ' + cpu_temp

        elif page == 8:
            lcd[0] = "emonPi Build:"
            lcd[1] = sd_image_version

        # If Shutdown button is pressed initiate shutdown sequence
        if GPIO.input(11) == 1:
            logger.info("shutdown button pressed")
            shutdown(lcd)

        # Wait up to one second or until the button is pressed.
        read, _, _ = select([pipe[0]], [], [], 1)
        if read:  # pipe is readable, consume the byte.
            try:
                read[0].read(1)
            except IOError:
                pass

if __name__ == '__main__':
    main()
