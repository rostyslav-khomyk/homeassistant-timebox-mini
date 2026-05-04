# Moving Text Implementation Specification

## Context

The current `timebox_mini` Home Assistant custom component exposes one service,
`timebox_mini.action`, with action names for clock, weather, static images, GIF
animations, volume, time, and brightness. The display path already supports:

- encoding an 11x11 RGBA image into the Timebox Mini pixel payload;
- wrapping a single frame as a static image command (`0x44`);
- wrapping many frames as animation frame commands (`0x49`);
- sending those packets over the existing RFCOMM Bluetooth socket on channel 4.

The upstream README lists moving text as TODO and points at
`DaveDavenport/timebox/examples/movingtext.py`. That reference implementation
scrolls by rendering a text window one column at a time and repeatedly sending
static images. For this integration, moving text should be implemented as
generated animation frames first, because it fits the existing service model and
is easier to test without long blocking service-call loops.

## Goals

- Add a Home Assistant service action that scrolls text on the 11x11 Timebox
  Mini display.
- Generate frames dynamically from service data instead of requiring users to
  create GIF assets manually.
- Keep the existing `timebox_mini.action` service backward compatible.
- Make rendering deterministic and testable without requiring Bluetooth
  hardware.
- Provide a clear manual validation path for a real Home Assistant installation
  with a paired Timebox Mini.

## Non-Goals

- Do not replace the Bluetooth transport or move to Home Assistant's modern BLE
  coordinator APIs in this feature.
- Do not add support for multiple Timebox devices or multiple Bluetooth
  adapters.
- Do not build a full text layout engine. The first version should support a
  compact, predictable matrix-font marquee.
- Do not rely on the Divoom cloud/mobile app.

## Proposed Service Contract

Extend `timebox_mini.action` with a new `action` value:

```yaml
action: moving_text
mac_addr: "11:75:58:7B:8B:29"
text: "HELLO TIMEBOX"
color: "#FFFFFF"
background_color: "#000000"
speed: 1
repeat: 1
direction: left
```

### New Fields

- `text`:
  Required for `moving_text`. String to display.
- `color`:
  Optional. Default `#FFFFFF`. Foreground text color.
- `background_color`:
  Optional. Default `#000000`. Frame background color.
- `speed`:
  Optional integer, default `1`, valid range `1..10`.
  Maps to the Timebox animation delay byte. The current GIF path uses
  `duration / 200`, so a first implementation should define speed as a friendly
  inverse and convert it to `delay = max(1, 11 - speed)`.
- `repeat`:
  Optional integer, default `1`, valid range `1..10`.
  Repeats the generated scroll frames before sending them.
- `direction`:
  Optional select, default `left`. First version should support `left`; keep
  the field extensible for `right` later.

### Entity State

After a successful call, update the current-view entity:

```python
hass.states.set(
    entity_id=DOMAIN + "." + slugify(mac) + "_current_view",
    new_state="moving_text",
    attributes={
        "text": text,
        "color": color,
        "background_color": background_color,
        "speed": speed,
        "repeat": repeat,
        "direction": direction,
    },
)
```

## Rendering Design

Use Pillow to render text into a wide monochrome or RGBA canvas, then crop an
11x11 viewport for each frame and reuse `process_image()` plus
`prepare_animation()`.

Recommended first implementation:

1. Add a tiny local renderer module, for example
   `custom_components/timebox_mini/text.py`.
2. Use `PIL.Image`, `PIL.ImageDraw`, and Pillow's bundled default font or a
   checked-in small bitmap font.
3. Normalize text to printable ASCII for the first version. Unsupported
   characters can render as spaces or `?`.
4. Create a source image:
   - width = rendered text width + `2 * TIMEBOX_SIZE`;
   - height = `TIMEBOX_SIZE`;
   - left and right padding = `TIMEBOX_SIZE`, so text enters and exits cleanly.
5. For each horizontal offset, crop an 11x11 frame and encode it with
   `process_image(frame)`.
6. Send with `prepare_animation(frames, delay=delay)`.

This approach keeps all protocol encoding in the existing functions. If the
device rejects very long generated animations, add a maximum frame count and fall
back to streaming static images in chunks.

## Code Changes

- `custom_components/timebox_mini/__init__.py`
  - Add constants: `ATTR_TEXT`, `ATTR_COLOR`, `ATTR_BACKGROUND_COLOR`,
    `ATTR_SPEED`, `ATTR_REPEAT`, `ATTR_DIRECTION`.
  - Add `moving_text` handling in `handle_action()`.
  - Prefer `try/finally` around device disconnect so render/send errors do not
    leak the socket.
- `custom_components/timebox_mini/services.yaml`
  - Add `moving_text` to the `action` selector.
  - Add selectors for the new fields.
- `custom_components/timebox_mini/text.py`
  - Add deterministic frame generation.
  - Keep this free of Home Assistant imports so it can be unit-tested directly.
- `README.md`
  - Document an example service call and current limitations.
- `manifest.json`
  - Bump the version once implementation is complete.

## Test Plan

### Local Unit Tests

Add `pytest` tests under `tests/` and a small test dependency setup.

Suggested tests:

- `mask()` escapes `0x01`, `0x02`, and `0x03`.
- `checksum()` returns LSB/MSB bytes.
- `process_image()` encodes an 11x11 RGBA image to the expected 182-byte payload.
- `render_moving_text_frames("HI", ...)` returns more than one frame.
- First and last moving-text frames are mostly background because of entry/exit
  padding.
- `prepare_animation()` produces one Timebox packet per frame and increments
  frame numbers.
- Long text either respects the agreed maximum frame count or is rejected with a
  clear validation error.

### Home Assistant Service Tests

Use a fake `Timebox` object or monkeypatch the `Timebox` class:

- Register the integration and call `timebox_mini.action` with
  `action: moving_text`.
- Assert the fake device receives animation packets.
- Assert the current-view entity state becomes `moving_text`.
- Assert service calls missing `text` fail validation or log a clear error.

### Manual Device Validation

Environment:

- Mac mini for local development.
- Home Assistant instance with Bluetooth/BLE adapter.
- Paired Divoom Timebox Mini already working with this integration.

Steps:

1. Install the fork or local custom component into Home Assistant.
2. Restart Home Assistant and confirm `timebox_mini.action` lists
   `moving_text`.
3. Call:

   ```yaml
   service: timebox_mini.action
   data:
     mac_addr: "<your Timebox MAC>"
     action: moving_text
     text: "DOOR OPEN"
     color: "#FF0000"
     background_color: "#000000"
     speed: 6
     repeat: 2
   ```

4. Confirm the text enters from the right, scrolls left, exits cleanly, and does
   not leave stale pixels.
5. Repeat with short text (`OK`), longer text (`GARAGE DOOR LEFT OPEN`), and
   mixed characters (`TEMP 21C`).
6. Confirm existing `image`, `animation`, `clock`, `weather`, `set_time`,
   `set_volume`, and `set_brightness` actions still work.
7. Check Home Assistant logs for socket errors, packet send errors, and service
   validation messages.

## Risks And Open Questions

- The existing integration uses classic Bluetooth RFCOMM sockets, not BLE GATT.
  That matches the current code and documented protocol, but it means Home
  Assistant OS/container Bluetooth access still matters.
- Very long text may create more animation packets than the Timebox accepts.
  The implementation should start with a conservative maximum and make the
  limit visible in validation/logging.
- Pillow's default font may be legible but not ideal at 11x11. If readability is
  poor on-device, add a checked-in 5x7 bitmap font and render per pixel.
- Home Assistant custom component setup is still synchronous. Sending many
  frames may block the service call briefly; keeping generated animations short
  and bounded is important.
