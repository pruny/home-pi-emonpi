#!/usr/bin/python
# -*- coding: utf-8 -*-

import lcddriver
import time
import os

#Get CPU temperature using 'vcgencmd measure_temp'
cpu_temp = ""
cpu_temp = os.popen('vcgencmd measure_temp').readline()
cpu_temp = (cpu_temp.replace("temp=","").replace("'C\n","\xDFC"))    # \337C or \xDFC is for °C on LCD

lcd = lcddriver.lcd(0x3f)

lcd.backlight =1
lcd.lcd_display_string("emonPi", 1)
lcd.lcd_display_string("test 123",2)
time.sleep()
lcd.backlight = 0
time.sleep(2)
lcd.backlight =1
lcd.lcd_clear()
lcd.lcd_display_string("CPU temperature:", 1)
lcd.lcd_display_string(">>> " + cpu_temp, 2)
time.sleep(5)
lcd.lcd_clear()
lcd.lcd_display_string("Backlight off", 1)
lcd.lcd_display_string("in 5 seconds..",2)
time.sleep(5)
lcd.backlight = 0
time.sleep(2)
lcd.backlight =1
lcd.lcd_clear()
lcd.lcd_display_string("Backlight on", 1)
lcd.lcd_display_string("end of test", 2)


