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
            timebox_protocol.set_sleep_sound(False, mode=0, safety_minutes=1),
            [
                0x01,
                0x06,
                0x00,
                0x40,
                0x03,
                0x04,
                0x00,
                0x00,
                0x47,
                0x00,
                0x02,
            ],
        )

    def test_sound_values_are_validated(self):
        with self.assertRaises(ValueError):
            timebox_protocol.set_volume(16)
        with self.assertRaises(ValueError):
            timebox_protocol.set_sleep_sound(True, mode=256)


if __name__ == "__main__":
    unittest.main()
