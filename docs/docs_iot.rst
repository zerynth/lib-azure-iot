.. module:: iot

*******************************
Microsoft Azure Iot Hub Library
*******************************

The Zerynth Microsoft Azure Iot Hub Library can be used to ease the connection to `Microsoft Azure Iot Hub <https://azure.microsoft.com/en-us/services/iot-hub/>`_.

It allows to make your device act as a Microsoft Azure Iot Hub Device which can be registered through Azure command line tools or Azure web dashboard.

    
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

    
.. method:: on_bound(bound_cbk)

        Set a callback to be called on cloud to device messages.

        :samp:`bound_cbk` callback will be called passing a string containing sent message and a dictionary containing sent properties::

            def bound_callback(msg, properties):
                print('c2d msg:', msg)
                print('with properties:', properties)

            my_device.on_bound(bound_callback)
        
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

        
.. method:: on_twin_update(twin_cbk)

        Set a callback to respond to cloud twin updates.

        :samp:`twin_cbk` callback will be called when a twin update is notified by the cloud, passing a dictionary containing desired twin and an integer representing current twin version::

            def twin_callback(twin, version):
                print('new twin version:', version)
                print(twin)

            my_device.on_twin_update(twin_callback)

        It is possible for :samp:`twin_cbk` to return a dictionary which will be immediately sent as reported twin.

        
.. method:: report_twin(reported, wait_confirm=True, timeout=1000)

        Report :samp:`reported` twin.

        :samp:`reported` twin must be a dictionary and will be sent as JSON string.
        It is possible to not wait for cloud confirmation setting :samp:`wait_confirm` to false or to set a custom :samp:`timeout` (:code:`-1` to wait forever) for the confirmation process which could lead to :code:`TimeoutException`. 

        An integer status code is returned after cloud confirmation.

        
.. method:: get_twin(timeout=1000)

        Get current twin containing desired and reported fields.
        It is possible set a custom :samp:`timeout` (:code:`-1` to wait forever) for the process which could lead to :code:`TimeoutException`. 

        An integer status code is returned after cloud response along with received :samp:`twin` JSON-parsed dictionary.

        
.. method:: publish_event(event, properties)

        Publish a new event :samp:`event` with custom :samp:`properties`.
        :samp:`event` must be a dictionary and will be sent as json string.
        :samp:`properties` must be a dictionary and will be sent as an url-encoded property bag.

        
