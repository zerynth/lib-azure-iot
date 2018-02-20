# Azure IoT Direct methods and messages
# Created at 2017-10-03 08:49:48.182639

import streams
import json
from wireless import wifi

# choose a wifi chip supporting secure sockets
from espressif.esp32net import esp32wifi as wifi_driver

import requests
# import azure iot module
from azure.iot import iot

# import helpers functions to easily load keys and device configuration
import helpers

# DEVICE KEY FILE MUST BE PLACED INSIDE PROJECT FOLDER
new_resource('private.base64.key')
# set device configuration inside this json file
new_resource('device.conf.json')

# define a callback for cloud to device messages
def bound_callback(msg, properties):
    print('received msg:', msg)
    print('with properties:', properties)

# define a callback for a cloud direct method
def send_something(method_payload):
    return (0,{'something': random(0,10)})

streams.serial()
wifi_driver.auto_init()

# place here your wifi configuration
wifi.link("SSID",wifi.WIFI_WPA2,"PSW")

pkey = helpers.load_key('private.base64.key')
device_conf = helpers.load_device_conf()
publish_period = 5000
sample_th = 5

# choose an appropriate way to get a valid timestamp (may be available through hardware RTC)
def get_timestamp():
    user_agent = {"user-agent": "curl/7.56.0"}
    return json.loads(requests.get('http://now.httpbin.org', headers=user_agent).content)['now']['epoch']

# create an azure iot device instance, connect to mqtt broker, set bound and method callbacks and start mqtt reception loop
device = iot.Device(device_conf['hub_id'], device_conf['device_id'], device_conf['api_version'], pkey, get_timestamp)
device.mqtt.connect()

device.on_bound(bound_callback)
device.on_method('get', send_something)

device.mqtt.loop()

while True:
    print('wait for directives from the Cloud...')
    sleep(5000)

