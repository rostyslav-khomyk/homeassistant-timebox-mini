"""Small, device-specific Timebox Mini protocol helpers."""


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


def set_sleep_sound(enabled, mode=0, safety_minutes=1):
    """Start or stop a built-in Timebox Mini sleep sound.

    The one-minute device timer is a fail-safe. The integration normally sends
    an explicit stop command after the requested short attention duration.
    """
    if not 0 <= mode <= 255:
        raise ValueError("Timebox sound mode must be between 0 and 255")
    if not 1 <= safety_minutes <= 255:
        raise ValueError("Timebox sound safety timer must be between 1 and 255 minutes")
    return build_command(0x40, safety_minutes, mode, 0xFF if enabled else 0x00)
