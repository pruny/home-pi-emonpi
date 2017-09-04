#!/usr/bin/python

import RPi.GPIO as GPIO
import time

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BOARD)

pin = 24

def reset():
  GPIO.setup(pin, GPIO.OUT)
  GPIO.output(pin, GPIO.HIGH)
  time.sleep(0.32)
  GPIO.output(pin, GPIO.LOW)

print "Reset ATMEGA using autoreset DTR on GPIO Pin "
time.sleep(1)

reset()

time.sleep(1)
print "JOB done, check on emonPiLCD!"

GPIO.cleanup()
exit