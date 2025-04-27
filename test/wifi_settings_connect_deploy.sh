#!/bin/bash -xe

S=~/Projects/rpi-pico/pico-wifi-settings

cd ~/Projects/rpi-pico/pico-extras/src/rp2_common/wifi_settings_connect

cp $S/src/wifi_settings_connect.c .
cp $S/src/wifi_settings_flash_range.c .
cp $S/src/wifi_settings_flash_storage.c .
cp $S/src/wifi_settings_hostname.c .

cd include/wifi_settings

cp $S/include/wifi_settings/wifi_settings_configuration.h .
cp $S/include/wifi_settings/wifi_settings_connect.h .
cp $S/include/wifi_settings/wifi_settings_connect_internal.h .
cp $S/include/wifi_settings/wifi_settings_flash_range.h .
cp $S/include/wifi_settings/wifi_settings_flash_storage.h .
cp $S/include/wifi_settings/wifi_settings_hostname.h .

cd ~/Projects/rpi-pico/pico-playground/wifi_settings_connect/example

cp $S/example/example.c .
cp $S/example/lwipopts.h .
