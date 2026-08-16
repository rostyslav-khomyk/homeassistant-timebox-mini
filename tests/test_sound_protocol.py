import importlib.util
from pathlib import Path
import unittest


MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "timebox_mini"
    / "protocol.py"
)
SPEC = importlib.util.spec_from_file_location("timebox_protocol", MODULE_PATH)
timebox_protocol = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(timebox_protocol)


class SoundProtocolTest(unittest.TestCase):
    class FakeDevice:
        def __init__(self):
            self.sent = []

        def send(self, packet):
            self.sent.append(packet)

    def test_set_volume_frame(self):
        self.assertEqual(
            timebox_protocol.set_volume(4),
            [0x01, 0x04, 0x00, 0x08, 0x04, 0x10, 0x00, 0x02],
        )

    def test_start_sleep_sound_frame(self):
        self.assertEqual(
            timebox_protocol.set_sleep_sound(True, mode=0, safety_minutes=1),
            [
                0x01,
                0x06,
                0x00,
                0x40,
                0x03,
                0x04,
                0x00,
                0xFF,
                0x46,
                0x03,
                0x04,
                0x02,
            ],
        )

    def test_stop_sleep_sound_frame(self):
        self.assertEqual(
            timebox_protocol.set_sleep_sound(False, mode=0),
            [
                0x01,
                0x06,
                0x00,
                0x40,
                0x00,
                0x00,
                0x00,
                0x46,
                0x00,
                0x02,
            ],
        )

    def test_sound_values_are_validated(self):
        with self.assertRaises(ValueError):
            timebox_protocol.set_volume(16)
        with self.assertRaises(ValueError):
            timebox_protocol.set_sleep_sound(True, mode=256)
        with self.assertRaises(ValueError):
            timebox_protocol.set_sleep_sound(True, safety_minutes=0)

    def test_attention_sound_uses_working_default_and_always_stops(self):
        device = self.FakeDevice()
        sleeps = []

        timebox_protocol.play_attention_sound(
            device,
            sleep=lambda duration: sleeps.append(duration),
        )

        self.assertEqual(sleeps, [3.0])
        self.assertEqual(
            device.sent,
            [
                timebox_protocol.set_volume(8),
                timebox_protocol.set_sleep_sound(True, mode=4),
                timebox_protocol.set_sleep_sound(False, mode=4),
            ],
        )

    def test_attention_sound_stops_when_sleep_fails(self):
        device = self.FakeDevice()

        def fail(_duration):
            raise RuntimeError("interrupted")

        with self.assertRaises(RuntimeError):
            timebox_protocol.play_attention_sound(device, sleep=fail)

        self.assertEqual(
            device.sent[-1],
            timebox_protocol.set_sleep_sound(False, mode=4),
        )


if __name__ == "__main__":
    unittest.main()
