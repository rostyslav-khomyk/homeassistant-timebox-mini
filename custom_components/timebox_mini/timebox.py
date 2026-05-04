import logging
import socket
import time

_LOGGER = logging.getLogger(__name__)

BTPROTO_RFCOMM = 3
TIMEBOX_HELLO = bytes([0, 5, 72, 69, 76, 76, 79, 0])
ACK_TIMEOUT = 2.0
CONNECT_TIMEOUT = 10.0
HELLO_TIMEOUT = 0.5
DEFAULT_SEND_RETRIES = 2


class TimeboxAcknowledgementError(Exception):
    """Raised when the Timebox does not acknowledge a sent command."""


def checksum(payload):
    csum = sum(payload)
    return [csum & 0x00ff, csum >> 8]


def unmask(data):
    unmasked = []
    escape_next = False
    for item in data:
        if escape_next:
            unmasked.append(item - 0x03)
            escape_next = False
        elif item == 0x03:
            escape_next = True
        else:
            unmasked.append(item)
    return unmasked


def decode_message(message):
    if len(message) < 4 or message[0] != 0x01 or message[-1] != 0x02:
        raise ValueError("Invalid Timebox message delimiters")

    payload_with_checksum = unmask(message[1:-1])
    if len(payload_with_checksum) < 3:
        raise ValueError("Invalid Timebox message length")

    payload = payload_with_checksum[:-2]
    message_checksum = payload_with_checksum[-2:]
    if checksum(payload) != message_checksum:
        raise ValueError("Invalid Timebox message checksum")

    return payload


def infer_command(package):
    try:
        payload = decode_message(list(package))
    except ValueError:
        return None

    if len(payload) < 3:
        return None
    return payload[2]


class Timebox:
    debug = False

    def __init__(self, target):
        self._recv_buffer = bytearray()
        if isinstance(target, socket.socket):
            self.sock = target
            self.addr, _ = self.sock.getpeername()
        else:
            self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, BTPROTO_RFCOMM)
            self.addr = target
            self.sock.settimeout(CONNECT_TIMEOUT)
            self.sock.connect((self.addr, 4))
            self.sock.settimeout(ACK_TIMEOUT)

    def connect(self):
        if (not self.sock):
            self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, BTPROTO_RFCOMM)
            self.sock.settimeout(CONNECT_TIMEOUT)
            self.sock.connect((self.addr, 4))
            self.sock.settimeout(ACK_TIMEOUT)
        self._drain_initial_hello()

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def send(self, package, recv=True, expected_command=None, retries=DEFAULT_SEND_RETRIES):
        package_bytes = bytes(bytearray(package))
        expected_command = expected_command if expected_command is not None else infer_command(package_bytes)
        last_error = None

        for attempt in range(retries + 1):
            self.sock.sendall(package_bytes)
            _LOGGER.debug("-> %s" % [hex(b)[2:].zfill(2) for b in package])
            _LOGGER.debug("Bytes sent : %d" % len(package_bytes))

            if not recv:
                return None

            try:
                return self.receive_ack(expected_command=expected_command)
            except TimeboxAcknowledgementError as err:
                last_error = err
                if attempt < retries:
                    _LOGGER.warning(
                        "No acknowledgement for Timebox command %s, retrying (%d/%d)",
                        self._format_command(expected_command),
                        attempt + 1,
                        retries,
                    )

        raise last_error

    def send_raw(self, bts):
        self.sock.send(bts)

    def receive_ack(self, expected_command=None, timeout=ACK_TIMEOUT):
        previous_timeout = self.sock.gettimeout()
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                message = self._pop_message()
                if message is not None:
                    try:
                        payload = decode_message(message)
                    except ValueError as err:
                        _LOGGER.debug("Ignoring invalid Timebox response: %s", err)
                        continue

                    _LOGGER.debug("<- %s" % [hex(h)[2:].zfill(2) for h in payload])
                    if self._is_ack(payload, expected_command):
                        return payload

                    if self._is_nack(payload, expected_command):
                        raise TimeboxAcknowledgementError(
                            "Timebox rejected command %s" % self._format_command(expected_command)
                        )

                    _LOGGER.debug("Ignoring unexpected Timebox response: %s", payload)
                    continue

                remaining = max(0.0, deadline - time.monotonic())
                if remaining == 0:
                    break

                try:
                    self.sock.settimeout(remaining)
                    chunk = self.sock.recv(256)
                except socket.timeout:
                    break

                if not chunk:
                    break

                self._recv_buffer.extend(chunk)
        finally:
            self.sock.settimeout(previous_timeout)

        raise TimeboxAcknowledgementError(
            "Timed out waiting for acknowledgement for command %s" % self._format_command(expected_command)
        )

    def _drain_initial_hello(self):
        previous_timeout = self.sock.gettimeout()
        try:
            self.sock.settimeout(HELLO_TIMEOUT)
            try:
                chunk = self.sock.recv(256)
            except socket.timeout:
                return

            if not chunk:
                return

            self._recv_buffer.extend(chunk)
            if self._consume_hello():
                _LOGGER.debug("<- TIMEBOX HELLO")
        finally:
            self.sock.settimeout(previous_timeout)

    def _consume_hello(self):
        if self._recv_buffer.startswith(TIMEBOX_HELLO):
            del self._recv_buffer[:len(TIMEBOX_HELLO)]
            return True
        return False

    def _pop_message(self):
        while self._recv_buffer:
            if self._consume_hello():
                continue

            start = self._recv_buffer.find(0x01)
            if start == -1:
                _LOGGER.debug("Dropping non-message Timebox response bytes: %s", list(self._recv_buffer))
                self._recv_buffer.clear()
                return None

            if start > 0:
                _LOGGER.debug("Dropping leading Timebox response bytes: %s", list(self._recv_buffer[:start]))
                del self._recv_buffer[:start]

            end = self._recv_buffer.find(0x02, 1)
            if end == -1:
                return None

            message = list(self._recv_buffer[:end + 1])
            del self._recv_buffer[:end + 1]
            return message

        return None

    def _is_ack(self, payload, expected_command):
        if len(payload) < 5 or payload[2] != 0x04 or payload[4] != 0x55:
            return False
        return expected_command is None or payload[3] == expected_command

    def _is_nack(self, payload, expected_command):
        if len(payload) < 2 or payload[-1] != 0xaa:
            return False
        return expected_command is None or payload[-2] == expected_command

    def _format_command(self, command):
        if command is None:
            return "unknown"
        return "0x%s" % hex(command)[2:].zfill(2)
