#!/bin/bash
echo "emonPi Update Started"
echo  `date`
echo "Getting latest emonPi release info from github"
download_url="$(curl -s https://api.github.com/repos/openenergymonitor/emonpi/releases | grep browser_download_url | head -n 1 | cut -d '"' -f 4)"
version="$(curl -s https://api.github.com/repos/openenergymonitor/emonpi/releases | grep tag_name | head -n 1 |  cut -d '"' -f 4)"
echo "Latest emonPi firmware: V"$version

echo "downloading latest emonPi firmware from github releases:"
echo $download_url
echo "Saving to /home/pi/data/firmware/emonPi-"$version".hex"

if [ ! -d /home/pi/data/firmware ]; then
  mkdir /home/pi/data/firmware
fi

wget -q $download_url -O /home/pi/data/firmware/emonPi-$version.hex

if [ -f /home/pi/data/firmware/emonPi-$version.hex ]; then
  sudo service emonhub stop
  echo
  echo "================================="
  echo "emonPi update started"
  echo "================================="
  echo
  echo "Flashing ATMEGA with emonPi-V" $version
  echo
  avrdude -v -c arduino -p ATMEGA328P -P /dev/ttyAMA0 -b 57600 -U flash:w:/home/pi/data/firmware/emonPi-$version.hex
  sudo service emonhub start
  echo "Flashing ATMEGA with emonPi-V" $version " done"
else
 echo "Firmware download failed...check network connection"
fi
