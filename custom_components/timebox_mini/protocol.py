"""Small, device-specific Timebox Mini protocol helpers."""

import time


def mask(values):
    """Escape Timebox framing bytes inside a command."""
    masked = []
    for value in values:
        if 0x01 <= value <= 0x03:
            masked.extend((0x03, value + 0x03))
        else:
            masked.append(value)
    return masked


def build_command(command, *arguments):
    """Build a framed Timebox command with its little-endian checksum."""
    length = 1 + len(arguments) + 2
    payload = [length & 0xFF, (length >> 8) & 0xFF, command, *arguments]
    checksum = sum(payload)
    return [
        0x01,
        *mask(payload),
        *mask((checksum & 0xFF, (checksum >> 8) & 0xFF)),
        0x02,
    ]


def set_volume(level):
    """Set the Timebox Mini's global speaker volume (0-15)."""
    if not 0 <= level <= 15:
        raise ValueError("Timebox volume must be between 0 and 15")
    return build_command(0x08, level)


def set_sleep_sound(enabled, mode=0, safety_minutes=None):
    """Start or stop a built-in Timebox Mini sleep sound.

    Starting the sound uses a one-minute fail-safe. Stopping it must send a
    zero-minute timer as well as the disabled flag; otherwise the Mini keeps
    the shutdown countdown after returning to another view.
    """
    if safety_minutes is None:
        safety_minutes = 1 if enabled else 0
    if not 0 <= mode <= 255:
        raise ValueError("Timebox sound mode must be between 0 and 255")
    minimum_minutes = 1 if enabled else 0
    if not minimum_minutes <= safety_minutes <= 255:
        raise ValueError(
            "Timebox sound timer must be between "
            f"{minimum_minutes} and 255 minutes"
        )
    return build_command(0x40, safety_minutes, mode, 0xFF if enabled else 0x00)


def play_attention_sound(dev, mode=4, volume=8, duration=3.0, sleep=time.sleep):
    """Play a built-in sound briefly and always send the stop command.

    Sleep-sound mode owns the Timebox Mini display, so callers should finish
    this cue before sending custom image or moving-text frames.
    """
    dev.send(set_volume(volume))
    dev.send(set_sleep_sound(True, mode=mode))
    try:
        sleep(duration)
    finally:
        dev.send(set_sleep_sound(False, mode=mode))
