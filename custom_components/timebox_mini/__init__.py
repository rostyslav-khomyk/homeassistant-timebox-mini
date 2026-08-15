from PIL import Image
from colour import Color
from homeassistant.const import CONF_HOST, CONF_PORT, EVENT_HOMEASSISTANT_STOP
import homeassistant.helpers.config_validation as cv
from homeassistant.util import slugify
from itertools import product
from .text import render_moving_text_frames
from .timebox import (
    DEFAULT_PROXY_PORT,
    DEFAULT_RFCOMM_CHANNEL,
    DEFAULT_SEND_RETRIES,
    Timebox,
    TimeboxAcknowledgementError,
)
import datetime
import logging
import math
import os
import time
import voluptuous as vol

# Width/height of the Timebox (11x11 for the Mini), can be changed for other Timebox support (untested)
TIMEBOX_SIZE = 11

# initial connection reply
TIMEBOX_HELLO = [0, 5, 72, 69, 76, 76, 79, 0]

_LOGGER = logging.getLogger(__name__)
dir_path = os.path.dirname(os.path.realpath(__file__))

# HomeAssistant service definitions
DOMAIN = "timebox_mini"
ATTR_MAC = "mac_addr"
ATTR_ACTION = "action"
ATTR_IMAGE = "image"
ATTR_ANIM = "animation"
ATTR_VOLUME = "volume"
ATTR_BRIGHTNESS = "brightness"
ATTR_TEXT = "text"
ATTR_COLOR = "color"
ATTR_BACKGROUND_COLOR = "background_color"
ATTR_SPEED = "speed"
ATTR_REPEAT = "repeat"
ATTR_DIRECTION = "direction"
ATTR_ANIMATION_FRAME_COUNT = "animation_frame_count"
ATTR_TEXT_FRAME_COUNT = "text_frame_count"
CONF_RFCOMM_CHANNEL = "rfcomm_channel"
CONF_DEVICE_ADDR = "device_addr"

DEFAULT_MOVING_TEXT_COLOR = [255, 255, 255]
DEFAULT_MOVING_TEXT_BACKGROUND_COLOR = [0, 0, 0]
MAX_ANIMATION_FRAMES = 256
LAST_ANIMATION_FRAME_COUNTS = {}
TIMEBOX_CONNECTIONS = {}
TIMEBOX_PROXY_HOST = None
TIMEBOX_PROXY_PORT = DEFAULT_PROXY_PORT
TIMEBOX_RFCOMM_CHANNEL = DEFAULT_RFCOMM_CHANNEL


CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_DEVICE_ADDR): cv.string,
                vol.Optional(CONF_HOST): cv.string,
                vol.Optional(CONF_PORT, default=DEFAULT_PROXY_PORT): cv.port,
                vol.Optional(CONF_RFCOMM_CHANNEL, default=DEFAULT_RFCOMM_CHANNEL): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=30)
                ),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


VIEWTYPES = {
    "clock": 0x00,
    "temp": 0x01,
    "off": 0x02,
    "anim": 0x03,
    "graph": 0x04,
    "image": 0x05,
    "stopwatch": 0x06,
    "scoreboard": 0x07
}


def switch_view(type):
    h = [0x04, 0x00, 0x45, VIEWTYPES[type]]
    ck1, ck2 = checksum(sum(h))
    return [0x01] + mask(h) + mask([ck1, ck2]) + [0x02]


# 0x01 Start of message
# 0x02 End of Message
# 0x03 Mask following byte

def color_comp_conv(cc):
    cc = max(0.0, min(1.0, cc))
    return int(math.floor(255 if cc == 1.0 else cc * 256.0))


def color_convert(rgb):
    return [color_comp_conv(c) for c in rgb]


def unmask(bytes, index=0):
    try:
        index = bytes.index(0x03, index)
    except ValueError:
        return bytes

    _bytes = bytes[:]
    _bytes[index + 1] = _bytes[index + 1] - 0x03
    _bytes.pop(index)
    return unmask(_bytes, index + 1)


def mask(bytes):
    _bytes = []
    for b in bytes:
        if (b == 0x01):
            _bytes = _bytes + [0x03, 0x04]
        elif (b == 0x02):
            _bytes = _bytes + [0x03, 0x05]
        elif (b == 0x03):
            _bytes = _bytes + [0x03, 0x06]
        else:
            _bytes += [b]

    return _bytes


def checksum(s):
    ck1 = s & 0x00ff
    ck2 = s >> 8
    return ck1, ck2


def set_time_color(r, g, b, x=0x00, h24=True):
    head = [0x09, 0x00, 0x45, 0x00, 0x01 if h24 else 0x00]
    s = sum(head) + sum([r, g, b, x])
    ck1, ck2 = checksum(s)
    msg = [0x01] + mask(head) + mask([r, g, b, x]) + mask([ck1, ck2]) + [0x02]
    return msg


def set_temp_color(r, g, b, x, f=False):
    head = [0x09, 0x00, 0x45, 0x01, 0x01 if f else 0x00]
    s = sum(head) + sum([r, g, b, x])
    ck1, ck2 = checksum(s)
    msg = [0x01] + mask(head) + mask([r, g, b, x]) + mask([ck1, ck2]) + [0x02]
    return msg


def set_temp_unit(f=False):
    head = [0x09, 0x00, 0x45, 0x01, 0x01 if f else 0x00]
    ck1, ck2 = checksum(sum(head))
    msg = [0x01] + mask(head) + mask([ck1, ck2]) + [0x02]
    return msg


def set_brightness(value):
    head = [0x04, 0x00, 0x74, int(value)]
    ck1, ck2 = checksum(sum(head))
    msg = [0x01] + mask(head) + mask([ck1, ck2]) + [0x02]
    return msg


def clamp_int(value, default, minimum, maximum):
    try:
        value = int(value)
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def current_view_entity_id(mac):
    return DOMAIN + "." + slugify(mac) + "_current_view"


def bound_animation_frame_count(frame_count):
    return max(0, min(MAX_ANIMATION_FRAMES, frame_count))


def get_last_animation_frame_count(hass, mac):
    entity_id = current_view_entity_id(mac)
    cached_count = LAST_ANIMATION_FRAME_COUNTS.get(entity_id)
    if cached_count is not None:
        return cached_count

    state = hass.states.get(entity_id)
    if state is None:
        return 0

    try:
        frame_count = int(state.attributes.get(ATTR_ANIMATION_FRAME_COUNT, 0))
    except (TypeError, ValueError):
        frame_count = 0

    if frame_count > 0:
        return bound_animation_frame_count(frame_count)

    if state.state != "moving_text":
        return 0

    try:
        repeat = clamp_int(state.attributes.get(ATTR_REPEAT), 1, 1, 10)
        frames = render_moving_text_frames(
            state.attributes.get(ATTR_TEXT, ""),
            color=state.attributes.get(ATTR_COLOR, DEFAULT_MOVING_TEXT_COLOR),
            background_color=state.attributes.get(ATTR_BACKGROUND_COLOR, DEFAULT_MOVING_TEXT_BACKGROUND_COLOR),
            direction=state.attributes.get(ATTR_DIRECTION, "left"),
            size=TIMEBOX_SIZE,
        )
        return bound_animation_frame_count(len(frames) * repeat)
    except Exception as e:
        _LOGGER.debug("Could not infer previous moving text frame count for %s: %s", mac, e)
        return 0


def set_last_animation_frame_count(mac, frame_count):
    LAST_ANIMATION_FRAME_COUNTS[current_view_entity_id(mac)] = bound_animation_frame_count(frame_count)


def get_timebox(mac):
    dev = TIMEBOX_CONNECTIONS.get(mac)
    if dev is None:
        dev = Timebox(
            mac,
            proxy_host=TIMEBOX_PROXY_HOST,
            proxy_port=TIMEBOX_PROXY_PORT,
            rfcomm_channel=TIMEBOX_RFCOMM_CHANNEL,
        )
        TIMEBOX_CONNECTIONS[mac] = dev
        _LOGGER.debug("Connected to %s", mac)
    else:
        if not dev.sock:
            dev.connect()
        _LOGGER.debug("Reusing connection to %s", mac)
    return dev


def close_timebox(mac):
    dev = TIMEBOX_CONNECTIONS.pop(mac, None)
    if dev is None:
        return

    try:
        dev.disconnect()
    except Exception as e:
        _LOGGER.debug("Error disconnecting from %s: %s", mac, e)


def close_all_timeboxes(event=None):
    for mac in list(TIMEBOX_CONNECTIONS):
        close_timebox(mac)


def pad_animation_tail(frames, frame_count, blank_frame):
    target_frame_count = max(frame_count, len(frames))
    if target_frame_count > MAX_ANIMATION_FRAMES:
        raise ValueError(
            "Animation generated %d frames; maximum is %d. Use shorter text/animation or a lower repeat value."
            % (target_frame_count, MAX_ANIMATION_FRAMES)
        )

    # The Timebox keeps older dynamic animation frames after the new last frame.
    # Overwrite that tail with blank frames so a shorter message does not replay stale content.
    if target_frame_count > len(frames):
        frames = frames + [blank_frame] * (target_frame_count - len(frames))

    return frames


def analyseImage(im):
    '''
    Pre-process pass over the image to determine the mode (full or additive).
    Necessary as assessing single frames isn't reliable. Need to know the mode
    before processing all frames.
    '''
    results = {
        'size': im.size,
        'mode': 'full',
    }
    try:
        while True:
            if im.tile:
                tile = im.tile[0]
                update_region = tile[1]
                update_region_dimensions = update_region[2:]
                if update_region_dimensions != im.size:
                    results['mode'] = 'partial'
                    break
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    im.seek(0)
    return results


def getFrames(im):
    '''
    Iterate the GIF, extracting each frame.
    '''
    mode = analyseImage(im)['mode']

    last_frame = im.convert('RGBA')

    try:
        while True:
            new_frame = Image.new('RGBA', im.size)

            '''
            Is this file a "partial"-mode GIF where frames update a region of a different size to the entire image?
            If so, we need to construct the new frame by pasting it on top of the preceding frames.
            '''
            if mode == 'partial':
                new_frame.paste(last_frame)

            new_frame.paste(im, (0, 0), im.convert('RGBA'))
            yield new_frame

            last_frame = new_frame
            im.seek(im.tell() + 1)
    except EOFError:
        pass


def process_image(imagedata, sz=TIMEBOX_SIZE, scale=None):
    img = [0]
    bc = 0
    first = True

    if (scale):
        src = imagedata.resize((sz, sz), scale)
    else:
        src = imagedata.resize((sz, sz))

    for c in product(range(sz), range(sz)):
        y, x = c
        r, g, b, a = src.getpixel((x, y))

        if (first):
            img[-1] = ((r & 0xf0) >> 4) + (g & 0xf0) if a > 32 else 0
            img.append((b & 0xf0) >> 4) if a > 32 else img.append(0)
            first = False
        else:
            img[-1] += (r & 0xf0) if a > 32 else 0
            img.append(((g & 0xf0) >> 4) + (b & 0xf0)) if a > 32 else img.append(0)
            img.append(0)
            first = True
        bc += 1
    return img


def load_image(file, sz=TIMEBOX_SIZE, scale=None):
    with Image.open(file).convert("RGBA") as imagedata:
        return process_image(imagedata, sz, scale)


def load_gif_frames(imagedata, sz=TIMEBOX_SIZE, scale=None):
    for f in getFrames(imagedata):
        yield process_image(f, sz, scale)


def conv_image(data):
    head = [0xbd, 0x00, 0x44, 0x00, 0x0a, 0x0a, 0x04]
    data = data
    ck1, ck2 = checksum(sum(head) + sum(data))
    msg = [0x01] + head + mask(data) + mask([ck1, ck2]) + [0x02]
    return msg


def prepare_animation(frames, delay=0):
    head = [0xbf, 0x00, 0x49, 0x00, 0x0a, 0x0a, 0x04]

    ret = []

    fi = 0
    for f in frames:
        _head = head + [fi, delay]
        ck1, ck2 = checksum(sum(_head) + sum(f))
        msg = [0x01] + mask(_head) + mask(f) + mask([ck1, ck2]) + [0x02]
        fi += 1
        ret.append(msg)

    return ret


def send_animation(dev, frames, delay=0, retries=DEFAULT_SEND_RETRIES):
    packets = prepare_animation(frames, delay=delay)

    for attempt in range(retries + 1):
        try:
            for packet in packets[:-1]:
                dev.send(packet, recv=False)
            if packets:
                dev.send(packets[-1], recv=True, retries=0)
            return
        except TimeboxAcknowledgementError:
            if attempt >= retries:
                raise
            _LOGGER.warning("No acknowledgement for final animation frame, retrying full animation (%d/%d)",
                            attempt + 1, retries)


def send_static_frames(dev, frames, frame_delay=0.2):
    last_frame_index = len(frames) - 1

    for index, frame in enumerate(frames):
        dev.send(conv_image(frame), recv=index == last_frame_index)
        if index < last_frame_index:
            time.sleep(frame_delay)


def setup(hass, config):
    global TIMEBOX_PROXY_HOST, TIMEBOX_PROXY_PORT, TIMEBOX_RFCOMM_CHANNEL

    domain_config = config.get(DOMAIN, {}) or {}
    TIMEBOX_PROXY_HOST = domain_config.get(CONF_HOST)
    TIMEBOX_PROXY_PORT = domain_config.get(CONF_PORT, DEFAULT_PROXY_PORT)
    TIMEBOX_RFCOMM_CHANNEL = domain_config.get(CONF_RFCOMM_CHANNEL, DEFAULT_RFCOMM_CHANNEL)

    if TIMEBOX_PROXY_HOST:
        _LOGGER.info(
            "Using Timebox Bluetooth proxy at %s:%d (RFCOMM channel %d)",
            TIMEBOX_PROXY_HOST,
            TIMEBOX_PROXY_PORT,
            TIMEBOX_RFCOMM_CHANNEL,
        )

    def handle_action(call):
        mac = call.data.get(ATTR_MAC, "00:00:00:00:00:00")
        action = call.data.get(ATTR_ACTION, "weather")

        if mac == "":
            _LOGGER.error("MAC address not specified, aborting service call")
            return

        try:
            dev = get_timebox(mac)
        except Exception as e:
            _LOGGER.error('Error connecting to %s : %s' % (mac, e))
            return

        try:
            c = color_convert(Color("white").get_rgb())

            if action == "image":
                image = call.data.get(ATTR_IMAGE, "home_assistant_black")
                _LOGGER.debug('Action : image %s' % (dir_path + "/matrices/" + image + ".png"))
                dev.send(conv_image(load_image(dir_path + "/matrices/" + image + ".png")))
                hass.states.set(entity_id=DOMAIN + "." + slugify(mac) + "_current_view",
                                new_state=action,
                                attributes={'image': image})

            elif action == "animation":
                anim = call.data.get(ATTR_ANIM, "orange_warning")
                _LOGGER.debug('Action : animation %s' % (dir_path + "/animations/" + anim + ".gif"))
                frames = []
                imagedata = Image.open(dir_path + "/animations/" + anim + ".gif")
                # Get duration of first frame and use it for all animation
                delay = int(imagedata.info['duration']/200)
                if delay <= 0:
                    delay = 1
                for f in load_gif_frames(imagedata):
                    frames.append(f)
                previous_frame_count = get_last_animation_frame_count(hass, mac)
                blank_frame = process_image(Image.new("RGBA", (TIMEBOX_SIZE, TIMEBOX_SIZE), (0, 0, 0, 255)))
                frames = pad_animation_tail(frames, previous_frame_count, blank_frame)
                send_animation(dev, frames, delay=delay)
                hass.states.set(entity_id=DOMAIN + "." + slugify(mac) + "_current_view",
                                new_state=action,
                                attributes={
                                    'animation': anim,
                                    ATTR_ANIMATION_FRAME_COUNT: len(frames),
                                })
                set_last_animation_frame_count(mac, len(frames))

            elif action == "moving_text":
                text = call.data.get(ATTR_TEXT, "")
                color = call.data.get(ATTR_COLOR, DEFAULT_MOVING_TEXT_COLOR)
                background_color = call.data.get(ATTR_BACKGROUND_COLOR, DEFAULT_MOVING_TEXT_BACKGROUND_COLOR)
                speed = clamp_int(call.data.get(ATTR_SPEED), 10, 1, 10)
                repeat = clamp_int(call.data.get(ATTR_REPEAT), 1, 1, 10)
                direction = call.data.get(ATTR_DIRECTION, "left")
                delay = max(1, 11 - speed)
                frame_delay = delay * 0.2
                rendered_frames = render_moving_text_frames(
                    text,
                    color=color,
                    background_color=background_color,
                    direction=direction,
                    size=TIMEBOX_SIZE,
                )
                frames = []
                for _ in range(repeat):
                    frames.extend(process_image(frame) for frame in rendered_frames)

                text_frame_count = len(frames)
                dynamic_frame_count = get_last_animation_frame_count(hass, mac)

                _LOGGER.debug('Action : moving_text %s', text)
                send_static_frames(dev, frames, frame_delay=frame_delay)
                hass.states.set(entity_id=DOMAIN + "." + slugify(mac) + "_current_view",
                                new_state=action,
                                attributes={
                                    'text': text,
                                    'color': color,
                                    'background_color': background_color,
                                    'speed': speed,
                                    'repeat': repeat,
                                    'direction': direction,
                                    ATTR_TEXT_FRAME_COUNT: text_frame_count,
                                    ATTR_ANIMATION_FRAME_COUNT: dynamic_frame_count,
                                })
                set_last_animation_frame_count(mac, dynamic_frame_count)

            elif action == "weather":
                _LOGGER.debug('Action : weather')
                dev.send(set_temp_color(c[0], c[1], c[2], 0xff))
                hass.states.set(entity_id=DOMAIN + "." + slugify(mac) + "_current_view",
                                new_state=action)

            elif action == "clock":
                _LOGGER.debug('Action : clock')
                dev.send(set_time_color(c[0], c[1], c[2], 0xff))
                hass.states.set(entity_id=DOMAIN + "." + slugify(mac) + "_current_view",
                                new_state=action)

            elif action == "set_volume":
                vol = call.data.get(ATTR_VOLUME, 4)
                _LOGGER.debug('Action : set_volume %d' % vol)
                head = [0x04, 0x00, 0x08]
                ck1, ck2 = checksum(sum(head) + vol)
                dev.send([0x01] + head + mask([vol]) + mask([ck1, ck2]) + [0x02])

            elif action == "set_time":
                _LOGGER.debug('Action : set_time')
                dt = datetime.datetime.now()
                head = [0x0A, 0x00, 0x18, dt.year % 100, int(dt.year / 100), dt.month, dt.day, dt.hour, dt.minute,
                        dt.second]
                s = sum(head)
                ck1, ck2 = checksum(s)
                dev.send([0x01] + mask(head) + mask([ck1, ck2]) + [0x02])

            elif action == "set_brightness":
                value = call.data.get(ATTR_BRIGHTNESS, 50)
                _LOGGER.debug('Action : set_brightness %d', value)
                dev.send(set_brightness(value))

            else:
                _LOGGER.error("Unknown Timebox Mini action '%s'", action)

        except Exception as e:
            close_timebox(mac)
            _LOGGER.error("Error running Timebox Mini action '%s' on %s: %s", action, mac, e)

    hass.services.register(DOMAIN, "action", handle_action)
    hass.bus.listen_once(EVENT_HOMEASSISTANT_STOP, close_all_timeboxes)

    # Return boolean to indicate that initialization was successfully.
    return True
