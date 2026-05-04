from PIL import Image, ImageColor, ImageDraw, ImageFont


DEFAULT_TEXT_COLOR = (255, 255, 255)
DEFAULT_BACKGROUND_COLOR = (0, 0, 0)


def _normalize_text(text):
    text = str(text or "").strip()
    if not text:
        raise ValueError("Moving text action requires a non-empty text value")
    return "".join(char if 32 <= ord(char) <= 126 else "?" for char in text)


def _normalize_color(value, default):
    if value in (None, ""):
        return default

    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(max(0, min(255, int(channel))) for channel in value)

    try:
        return tuple(ImageColor.getrgb(str(value))[:3])
    except ValueError as err:
        raise ValueError("Expected color as #RRGGBB, color name, or RGB list") from err


def render_moving_text_frames(
    text,
    color=DEFAULT_TEXT_COLOR,
    background_color=DEFAULT_BACKGROUND_COLOR,
    direction="left",
    size=11,
):
    text = _normalize_text(text)
    foreground = _normalize_color(color, DEFAULT_TEXT_COLOR)
    background = _normalize_color(background_color, DEFAULT_BACKGROUND_COLOR)
    direction = str(direction or "left").lower()

    if direction not in ("left", "right"):
        raise ValueError("Moving text direction must be 'left' or 'right'")

    font = ImageFont.load_default()
    measure = Image.new("RGBA", (1, 1), background + (255,))
    draw = ImageDraw.Draw(measure)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = max(1, bbox[2] - bbox[0])
    text_height = max(1, bbox[3] - bbox[1])

    canvas_width = text_width + (size * 2)
    canvas = Image.new("RGBA", (canvas_width, size), background + (255,))
    draw = ImageDraw.Draw(canvas)
    x = size - bbox[0]
    y = max(0, (size - text_height) // 2 - bbox[1])
    draw.text((x, y), text, font=font, fill=foreground + (255,))

    offsets = range(0, canvas_width - size + 1)
    if direction == "right":
        offsets = reversed(list(offsets))

    return [canvas.crop((offset, 0, offset + size, size)) for offset in offsets]
