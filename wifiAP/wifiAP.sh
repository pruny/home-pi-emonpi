#!/usr/bin/env bash

# Script to start / stop WiFi AP and bridge eth1
# https://github.com/openenergymonitor/emonpi/blob/master/docs/wifiAP.md
# Only works with BCM43143 e.g. RasPi3 / offical RasPi dongle
	
if [ $EUID -ne 0 ]; then
   echo "This script must be run as root"
   exit 1
fi


if [ -z "$1" ]; then
    echo "Please specify start or stop as argument"
    exit 1
fi


echo "WiFi AP only works with BCM43143 e.g. RasPi3"

read -n1 -r -p "Press space to continue...any key to exit" key

if [ "$key" = '' ]; then
    echo " "
    echo "Starting AP.....please wait process could take about 10-20s"
    echo "Wifi connection will now be lost...wait 30s then connect to SSID 'emonPi' SSID with password 'raspberry' then browse to http://192.168.42.1"
else
    exit 1
fi



rpi-rw

# TO DO - make script auto read type of WiFi driver in use and determine if it will work with this version of hostpad
#driver= basename $( readlink /sys/class/net/wlan0/device/driver ) | tr -d "\n"
#echo "$driver"
#driver="brcmfmac_sdio"
#if [ "${driver}" != "brcmfmac_sdio " ]; then
#    echo "Exiting Wifi AP requires rtl8192cu / brcmfmac_sdio driver (BCM43143) e.g. RasPi3 / offical RasPi dongle"
#    echo "Edimax can be used with different version of hostpad https://github.com/openenergymonitor/emonpi/blob/master/docs/wifiAP.md"
#    exit 1
#fi


if [ "$1" = "start" ]; then

	sudo ifdown wlan0
	sleep 4
	sudo ifconfig wlan0 down
	
	# if eth1 exists and is up then bridge to wlan0
	FOUND=`grep "eth1" /proc/net/dev`
    	if  [ -n "$FOUND" ] ; then
        	echo "eth1 up"
        	echo "Bridge eth1 (GSM dongle) to WiFi AP"
		# Remove bridge routes if exist to avoid duplicates 
        	sudo iptables -t nat -D POSTROUTING -o eth1 -j MASQUERADE >/dev/null 2>&1
        	sudo iptables -D FORWARD -i eth1 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT >/dev/null 2>&1
        	sudo iptables -D FORWARD -i wlan0 -o eth1 -j ACCEPT >/dev/null 2>&1
		# Add bridge nodes        	
		sudo iptables -t nat -A POSTROUTING -o eth1 -j MASQUERADE
        	sudo iptables -A FORWARD -i eth1 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT
		sudo iptables -A FORWARD -i wlan0 -o eth1 -j ACCEPT
    	fi
    
    	sleep 5
	echo "Set static IP addres of emonPi AP 192.168.42.1"
	sudo ifconfig wlan0 192.168.42.1
    	sleep 5
	# Start DHCP server to offer AP clients DHCP
	echo "Start isc-dhcp-server"
	sudo service isc-dhcp-server start
	sleep 5

	# Start AP -  /etc/hostapd/hostapd.conf
	echo "Start emonPi Wifi AP...."
	if [ ! -f /home/pi/data/dhcpd.leases]; then
		sudo touch /home/pi/data/dhcpd.leases
	fi
	sudo service hostapd start

fi

if [ "$1" = "stop" ]; then
# Stop Wifi AP and restore normal Managed Client STA mode
        echo "Stop hostapd Wifi AP"
        sudo service hostapd stop
        echo "Stop isc-dhcp-server"
        sudo service isc-dhcp-server stop
        sleep 5
        sudo ifconfig wlan0 down
        sudo ifdown wlan0
        sleep 5
        sudo ifup wlan0
        
        # Remove bridge routes
        sudo iptables -t nat -D POSTROUTING -o eth1 -j MASQUERADE >/dev/null 2>&1
        sudo iptables -D FORWARD -i eth1 -o wlan0 -m state --state RELATED,ESTABLISHED -j ACCEPT >/dev/null 2>&1
        sudo iptables -D FORWARD -i wlan0 -o eth1 -j ACCEPT >/dev/null 2>&1
fi
rpi-ro