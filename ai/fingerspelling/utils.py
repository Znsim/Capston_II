import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

_font_cache: dict = {}

_FONT_PATHS = [
    "C:/Windows/Fonts/malgun.ttf",
    "C:/Windows/Fonts/malgunbd.ttf",
    "C:/Windows/Fonts/gulim.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]


def get_font(size: int) -> ImageFont.FreeTypeFont:
    if size in _font_cache:
        return _font_cache[size]
    for fp in _FONT_PATHS:
        try:
            font = ImageFont.truetype(fp, size)
            _font_cache[size] = font
            return font
        except IOError:
            pass
    font = ImageFont.load_default()
    _font_cache[size] = font
    return font


def put_text_kr(img: np.ndarray, text: str, pos: tuple,
                font_size: int = 40, color: tuple = (0, 255, 0)) -> np.ndarray:
    """OpenCV BGR 이미지에 한글 텍스트를 렌더링."""
    img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(img_pil)
    draw.text(pos, text, font=get_font(font_size), fill=color)
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
