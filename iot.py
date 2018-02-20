# -*- coding: utf-8 -*-
# @Author: lorenzo
# @Date:   2017-09-21 16:17:16
# @Last Modified by:   Lorenzo
# @Last Modified time: 2017-11-13 15:27:14

"""
.. module:: iot

*******************************
Microsoft Azure Iot Hub Library
*******************************

The Zerynth Microsoft Azure Iot Hub Library can be used to ease the connection to `Microsoft Azure Iot Hub <https://azure.microsoft.com/en-us/services/iot-hub/>`_.

It allows to make your device act as a Microsoft Azure Iot Hub Device which can be registered through Azure command line tools or Azure web dashboard.

    """

import json
import ssl
import timers
import urlparse
import threading
from azure.sas import sas
from mqtt import mqtt

class AzureMQTTClient(mqtt.Client):

    def __init__(self, mqtt_id, hub_id, api_version, ssl_ctx, create_sas):
        mqtt.Client.__init__(self, mqtt_id, clean_session=False)
        self.hub_hostname = hub_id + '.azure-devices.net'
        # api version MANDATORY to allow some functionalities (e.g. direct methods, twin updates...)
        self.username = self.hub_hostname + '/' + mqtt_id + '/api-version=' + api_version
        self.ssl_ctx = ssl_ctx
        self.create_sas = create_sas

        self.last_reconnection_try = None

    def _reconnect_cb(self, _):
        tnow  = timers.now()
        tdiff = tnow - self.last_reconnection_try
        if tdiff > 10000:
            psw = self.create_sas() # get timestamp from a reliable source
        else:
            psw = self.create_sas(timestamp_diff = (tdiff // 1000))

        self.last_reconnection_try = tnow
        mqtt.Client.set_username_pw(self, self.username, password=psw)

    def connect(self, port=8883):
        self.last_reconnection_try = timers.now()
        mqtt.Client.set_username_pw(self, self.username, password=self.create_sas())
        mqtt.Client.connect(self, self.hub_hostname, 60, port=port, ssl_ctx=self.ssl_ctx, breconnect_cb=self._reconnect_cb)


class Device:
    """
================
The Device class
================

.. class:: Device(hub_id, device_id, api_version, key, timestamp_fn, token_lifetime=60)

        Create a Device instance representing a Microsoft Azure Iot Hub Device.

        The Device object will contain an mqtt client instance pointing to Microsoft Azure Iot Hub MQTT broker located at :samp:`hub_id.azure-devices.net`.
        The client is configured with :samp:`device_id` as MQTT id and is able to connect securely through TLS and authenticate through a `SAS <https://docs.microsoft.com/en-us/azure/storage/common/storage-dotnet-shared-access-signature-part-1>`_ token with a :samp:`token_lifetime` minutes lifespan.
        
        Valid tokens generation process needs current timestamp which will be obtained calling passed :samp:`timestamp_fn`.
        :samp:`timestamp_fn` has to be a Python function returning an integer timestamp.
        A valid base64-encoded primary or secondary key :samp:`key` is also needed.

        The :samp:`api_version` string is mandatory to enable some responses from Azure MQTT broker on specific topics.

        The client is accessible through :samp:`mqtt` instance attribute and exposes all :ref:`Zerynth MQTT Client methods <lib.zerynth.mqtt>` so that it is possible, for example, to setup
        custom callbacks on MQTT commands (though the Device class already exposes high-level methods to setup Azure specific callbacks).
        The only difference concerns :code:`mqtt.connect` method which does not require broker url and ssl context, taking them from Device configuration::

            def timestamp_fn():
                valid_timestamp = 1509001724
                return valid_timestamp

            key = "ZhmdoNjyBccLrTnku0JxxVTTg8e94kleWTz9M+FJ9dk="
            my_device = iot.Device('my-hub-id', 'my-device-id', '2017-06-30', key, timestamp_fn)
            my_device.mqtt.connect()
            ...
            my_device.mqtt.loop()

    """
    def __init__(self, hub_id, device_id, api_version, key, timestamp_fn, token_lifetime=60):
        self.ctx = ssl.create_ssl_context(options=ssl.CERT_NONE) # should add root...
        self.device_id = device_id
        self.hub_id = hub_id
        self.key = key
        self.timestamp_fn = timestamp_fn
        self.token_lifetime = token_lifetime
        self.mqtt = AzureMQTTClient(device_id, hub_id, api_version, self.ctx, self._create_sas)

        self.uri = hub_id + '.azure-devices.net/devices'

        self._bound_cbk = None
        self._method_cbks = None
        self._twin_cbk = None

        self._hub_res = False
        self._hub_res_event = False

    def _create_sas(self, timestamp_diff = None):
        if timestamp_diff is None:
            timestamp = self.timestamp_fn()
        else:
            timestamp = self._last_timestamp + timestamp_diff
        self._last_timestamp = timestamp

        ttl = timestamp + 60*self.token_lifetime

        return sas.generate(self.uri, self.key, ttl)

    def _decode_properties(self, topic, question=True):
        if question:
            return urlparse.parse_qs(topic.split('/?')[-1], unquote_key=True)
        return urlparse.parse_qs(topic.split('/')[-1], unquote_key=True)

    def _handle_bound(self, mqtt_client, mqtt_data):
        self._bound_cbk(mqtt_data['message'].payload, self._decode_properties(mqtt_data['message'].topic, question=False))

    def _is_bound(self, mqtt_data):
        if ('message' in mqtt_data):
            return mqtt_data['message'].topic.startswith('devices/' + self.device_id + '/messages/devicebound/')
        return False

    def on_bound(self, bound_cbk):
        """
.. method:: on_bound(bound_cbk)

        Set a callback to be called on cloud to device messages.

        :samp:`bound_cbk` callback will be called passing a string containing sent message and a dictionary containing sent properties::

            def bound_callback(msg, properties):
                print('c2d msg:', msg)
                print('with properties:', properties)

            my_device.on_bound(bound_callback)
        """
        if self._bound_cbk is None:
            self.mqtt.subscribe([['devices/' + self.device_id + '/messages/devicebound/#', 0]])
        self._bound_cbk = bound_cbk
        self.mqtt.on(mqtt.PUBLISH, self._handle_bound, self._is_bound)

    def _handle_method(self, mqtt_client, mqtt_data):
        tt = mqtt_data['message'].topic.split('/')
        method_name = tt[-2]
        if mqtt_data['message'].payload == 'null':
            method_body = None
        else:
            method_body = json.loads(mqtt_data['message'].payload)
        status, res_body = self._method_cbks[method_name](method_body)
        self.mqtt.publish('$iothub/methods/res/' + str(status) + '/' + tt[-1], json.dumps(res_body))

    def _is_method(self, mqtt_data):
        if ('message' in mqtt_data):
            return mqtt_data['message'].topic.startswith('$iothub/methods/POST/')
        return False

    def on_method(self, method_name, method_cbk):
        """
.. method:: on_method(method_name, method_cbk)

        Set a callback to respond to a direct method call.

        :samp:`method_cbk` callback will be called in response to :samp:`method_name` method, passing a dictionary containing method payload (should be a valid JSON)::

            def send_something(method_payload):
                if method_payload['type'] == 'random':
                    return (0, {'something': random(0,10)})
                deterministic = 5
                return (0, {'something': deterministic})

            my_device.on_method('get', send_something)

        :samp:`method_cbk` callback must return a tuple containing response status and a dictionary or None as response payload.

        """
        if self._method_cbks is None:
            self.mqtt.subscribe([['$iothub/methods/POST/#', 0]])
            self._method_cbks = {}
        self._method_cbks[method_name] = method_cbk
        self.mqtt.on(mqtt.PUBLISH, self._handle_method, self._is_method)

    def _handle_twin(self, mqtt_client, mqtt_data):
        version = self._decode_properties(mqtt_data['message'].topic)['$version']
        reported = self._twin_cbk(json.loads(mqtt_data['message'].payload), version)
        if reported is not None:
            self.report_twin(reported, wait_confirm=False) # confirm cannot be waited inside callback to not lock mqtt read loop (!)

    def _is_twin_update(self, mqtt_data):
        if ('message' in mqtt_data):
            return mqtt_data['message'].topic.startswith('$iothub/twin/PATCH/properties/desired/')
        return False

    def on_twin_update(self, twin_cbk):
        """
.. method:: on_twin_update(twin_cbk)

        Set a callback to respond to cloud twin updates.

        :samp:`twin_cbk` callback will be called when a twin update is notified by the cloud, passing a dictionary containing desired twin and an integer representing current twin version::

            def twin_callback(twin, version):
                print('new twin version:', version)
                print(twin)

            my_device.on_twin_update(twin_callback)

        It is possible for :samp:`twin_cbk` to return a dictionary which will be immediately sent as reported twin.

        """
        if self._twin_cbk is None:
            self.mqtt.subscribe([['$iothub/twin/PATCH/properties/desired/#', 0]])
        self._twin_cbk = twin_cbk
        self.mqtt.on(mqtt.PUBLISH, self._handle_twin, self._is_twin_update)

    def _handle_hub_res(self, mqtt_client, mqtt_data):
        tt = mqtt_data['message'].topic.split('/')
        self._hub_res_status = int(tt[-2])
        req_id = int(self._decode_properties(mqtt_data['message'].topic)['$rid'])
        if req_id == self._hub_reqid:
            self._hub_res = mqtt_data['message'].payload
            self._hub_res_event.set()

    def _is_hub_res(self, mqtt_data):
        if ('message' in mqtt_data):
            return mqtt_data['message'].topic.startswith('$iothub/twin/res/')
        return False

    def _hub_res_init(self):
        self.mqtt.subscribe([['$iothub/twin/res/#', 0]])
        self._hub_res = True
        self._hub_res_event = threading.Event()
        self._hub_reqid = -1
        self._hub_req_lock = threading.Lock()
        self.mqtt.on(mqtt.PUBLISH, self._handle_hub_res, self._is_hub_res)

    def report_twin(self, reported, wait_confirm=True, timeout=1000):
        """
.. method:: report_twin(reported, wait_confirm=True, timeout=1000)

        Report :samp:`reported` twin.

        :samp:`reported` twin must be a dictionary and will be sent as JSON string.
        It is possible to not wait for cloud confirmation setting :samp:`wait_confirm` to false or to set a custom :samp:`timeout` (:code:`-1` to wait forever) for the confirmation process which could lead to :code:`TimeoutException`. 

        An integer status code is returned after cloud confirmation.

        """
        if not self._hub_res:
            self._hub_res_init()
        self._hub_req_lock.acquire()
        status = None
        self._hub_reqid += 1
        self._hub_res_event.clear()
        self.mqtt.publish('$iothub/twin/PATCH/properties/reported/?$rid=' + str(self._hub_reqid), json.dumps(reported))
        if wait_confirm:
            rr = self._hub_res_event.wait(timeout=timeout)
            if rr == -1:
                self._hub_req_lock.release()
                raise TimeoutError
            status = self._hub_res_status
        self._hub_req_lock.release()
        return status

    def get_twin(self, timeout=1000):
        """
.. method:: get_twin(timeout=1000)

        Get current twin containing desired and reported fields.
        It is possible set a custom :samp:`timeout` (:code:`-1` to wait forever) for the process which could lead to :code:`TimeoutException`. 

        An integer status code is returned after cloud response along with received :samp:`twin` JSON-parsed dictionary.

        """
        if not self._hub_res:
            self._hub_res_init()
        self._hub_req_lock.acquire()
        status = None
        twin   = None
        self._hub_reqid += 1
        self._hub_res_event.clear()
        self.mqtt.publish('$iothub/twin/GET/?$rid=' + str(self._hub_reqid))
        rr = self._hub_res_event.wait(timeout=timeout)
        if rr == -1:
            self._hub_req_lock.release()
            raise TimeoutError
        status = self._hub_res_status
        if status == 200:
            twin   = json.loads(self._hub_res)
        self._hub_req_lock.release()
        return status, twin

    def publish_event(self, event, properties):
        """
.. method:: publish_event(event, properties)

        Publish a new event :samp:`event` with custom :samp:`properties`.
        :samp:`event` must be a dictionary and will be sent as json string.
        :samp:`properties` must be a dictionary and will be sent as an url-encoded property bag.

        """
        self.mqtt.publish('devices/' + self.device_id + '/messages/events/' + urlparse.urlencode(properties),
            json.dumps(event))
