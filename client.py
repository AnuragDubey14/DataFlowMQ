import paho.mqtt.client as mqtt
import os
import queue

class SimpleMQTTClient:
    def __init__(self, broker_address, topic, client_id, username=None, password=None, port=1883, keepalive=60,
                 ca_cert=None, client_cert=None, client_key=None):
        """
        Initialize the MQTT client.
        :param broker_address: MQTT broker's address.
        :param topic: Topic to subscribe to.
        :param port: MQTT broker port (default: 1883, 8883 for SSL/TLS).
        :param keepalive: Keepalive interval in seconds (default: 60).
        :param ca_cert: Path to the CA certificate (can be None for non-secure connection).
        :param client_cert: Path to the client certificate (can be None for non-secure connection).
        :param client_key: Path to the client private key (can be None for non-secure connection).
        """
        self.client_id = client_id
        self.client = mqtt.Client(client_id=self.client_id, protocol=mqtt.MQTTv311, reconnect_on_failure=True)
        self.broker_address = broker_address
        self.topic = topic
        self.port = port
        self.keepalive = keepalive
        self.connected = False
        self.data_queue = queue.Queue()

        if username and password:
            self.client.username_pw_set(username, password)

        # If certificates are provided, set up the secure connection (TLS/SSL)
        if ca_cert or client_cert or client_key:
            self.client.tls_set(ca_certs=ca_cert, certfile=client_cert, keyfile=client_key)
            self.client.tls_insecure_set(False)  # Set to True if certificate validation is not required (not recommended)

        # Bind event callbacks
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback for when the client connects to the broker.
        """
        if rc == 0:
            self.connected = True
            print(f"Connected to MQTT Broker at {self.broker_address}.")
            self.client.subscribe(self.topic)
            print(f"Subscribed to topic: {self.topic}")
        else:
            print(f"Failed to connect, return code {rc}")

    def on_disconnect(self, client, userdata, rc):
        """
        Callback for when the client disconnects from the broker.
        """
        self.connected = False
        print("Disconnected from the MQTT broker.")

    def on_message(self, client, userdata, message):
        """
        Callback for when a message is received from the broker.
        """
        print(f"Received message: {message.payload.decode()}")
        self.data_queue.put(message.payload.decode())

    def is_connected(self):
        """
        Check if the client is connected to the MQTT broker.
        :return: True if connected, False otherwise.
        """
        return self.connected

    def start(self):
        """
        Connect to the broker and start the loop in a non-blocking way.
        """
        try:
            self.client.connect(self.broker_address, self.port, self.keepalive)
            print(f"Attempting to connect to the broker at {self.broker_address}...")
            self.client.loop_start()  # Non-blocking loop
        except Exception as e:
            print(f"Error while connecting to the broker: {e}")

    def disconnect(self):
        """
        Disconnect from the MQTT broker.
        """
        print("Disconnecting from the MQTT broker...")
        self.client.loop_stop()  # Stop the loop
        self.client.disconnect()
        print("Disconnected.")

# Example usage
# if __name__ == "__main__":
#     broker_address = "137.117.79.12"  # Replace with your broker address
#     topic = "tusmart/maint/power/bypl/ss/23/2X/205"  # Replace with your topic
#     mqtt_client = SimpleMQTTClient(
#         broker_address,
#         topic,
#         client_id=f"DataSync/{os.getpid()}",
#         username="anurag",  # Replace with your username
#         password="dubey",  # Replace with your password
#         ca_cert=None,  # No CA certificate
#         client_cert=None,  # No client certificate
#         client_key=None  # No client key
#     )

#     # Start the client (non-secure connection)
#     mqtt_client.start()
#     print("Client Started")
