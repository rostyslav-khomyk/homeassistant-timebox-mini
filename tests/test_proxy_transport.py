import importlib.util
from pathlib import Path
import socket
import unittest
from unittest.mock import patch


MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "timebox_mini"
    / "timebox.py"
)
SPEC = importlib.util.spec_from_file_location("timebox_transport", MODULE_PATH)
timebox_transport = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(timebox_transport)


class FakeSocket:
    instances = []

    def __init__(self, *_args):
        self.timeout = None
        self.sent = []
        self.recv_chunks = [timebox_transport.TIMEBOX_HELLO]
        self.closed = False
        self.connected_to = None
        self.instances.append(self)

    def settimeout(self, timeout):
        self.timeout = timeout

    def gettimeout(self):
        return self.timeout

    def sendall(self, data):
        self.sent.append(bytes(data))

    def connect(self, address):
        self.connected_to = address

    def recv(self, _size):
        if self.recv_chunks:
            return self.recv_chunks.pop(0)
        raise socket.timeout

    def close(self):
        self.closed = True


class ProxyTransportTest(unittest.TestCase):
    def test_proxy_connect_and_disconnect_control_packets(self):
        fake_socket = FakeSocket()
        with patch.object(socket, "create_connection", return_value=fake_socket) as create_connection:
            dev = timebox_transport.Timebox(
                "11:75:58:3E:C1:B8",
                proxy_host="ble2hass.local",
                proxy_port=7777,
                rfcomm_channel=4,
            )

            create_connection.assert_called_once_with(
                ("ble2hass.local", 7777),
                timeout=timebox_transport.CONNECT_TIMEOUT,
            )
            self.assertEqual(
                fake_socket.sent[0],
                bytes.fromhex("69 11 75 58 3E C1 B8 04"),
            )

            dev.disconnect()

        self.assertEqual(
            fake_socket.sent[-1],
            bytes.fromhex("96 11 75 58 3E C1 B8"),
        )
        self.assertTrue(fake_socket.closed)

    def test_invalid_proxy_mac_is_rejected(self):
        with patch.object(socket, "create_connection", return_value=FakeSocket()):
            with self.assertRaisesRegex(ValueError, "Invalid Timebox Bluetooth MAC"):
                timebox_transport.Timebox("not-a-mac", proxy_host="ble2hass.local")

    def test_direct_transport_uses_configured_rfcomm_channel(self):
        FakeSocket.instances.clear()
        with patch.object(socket, "AF_BLUETOOTH", 31, create=True), patch.object(
            socket, "socket", FakeSocket
        ):
            dev = timebox_transport.Timebox(
                "11:75:58:3E:C1:B8",
                rfcomm_channel=7,
            )

            self.assertEqual(len(FakeSocket.instances), 1)
            fake_socket = FakeSocket.instances[0]
            self.assertEqual(fake_socket.connected_to, ("11:75:58:3E:C1:B8", 7))
            dev.disconnect()


if __name__ == "__main__":
    unittest.main()
