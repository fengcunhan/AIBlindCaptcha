# filename: captcha_generator.py
# -*- coding: utf-8 -*-
import os
import io
import math
import random
import string
from typing import Tuple, Optional, List

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2

"""
Time-encoded video CAPTCHA generator (Algorithm 2 inspired)
- If you have a depth map D: pixels within [tl, tu] move with noise (y + v*t), others stay static
- Else, we synthesize a binary mask from text or shape, then apply the same rule: mask pixels move, background static

Outputs: MP4 video bytes and ground-truth answer

Why this design:
- Single frames look like structured noise; only during playback, foreground reveals via motion coherence
- Resists frame-level OCR or spatial-only models; relies on temporal integration

Security notes:
- Do NOT hardcode secrets in code
- Always pair with server-side token and TTL
"""

# ----- Configs -----
DEFAULT_WIDTH = 640
DEFAULT_HEIGHT = 360
DEFAULT_FPS = 24
DEFAULT_DURATION_SEC = 4.0  # ~96 frames
DEFAULT_SPEED_PX_PER_FRAME = 1  # vertical offset per frame
DEFAULT_NOISE_BLOCK = 2  # speckle size
DEFAULT_NOISE_DENSITY = 0.5  # probability of white block
FONT_PATHS_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",       # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",    # Linux
    "C:\\Windows\\Fonts\\arial.ttf",                      # Windows
]

def _pick_font(size: int) -> ImageFont.FreeTypeFont:
    # Try to use better fonts for larger sizes
    if size >= 60:
        extended_paths = FONT_PATHS_CANDIDATES + [
            "/System/Library/Fonts/Helvetica.ttc",         # macOS
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",  # Linux Ubuntu
            "C:\\Windows\\Fonts\\calibri.ttf",             # Windows
        ]
    else:
        extended_paths = FONT_PATHS_CANDIDATES

    for p in extended_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except:
                continue
    # Fallback: PIL default bitmap font
    return ImageFont.load_default()

def _make_tiled_noise(h: int, w: int, block: int, density: float, seed: Optional[int] = None) -> np.ndarray:
    """
    Generate tileable binary noise pattern in blocks.
    Returns uint8 array [h, w], values in {0, 255}
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random.RandomState()

    gh = math.ceil(h / block)
    gw = math.ceil(w / block)
    grid = (rng.rand(gh, gw) < density).astype(np.uint8) * 255
    # Expand to pixels
    noise = np.kron(grid, np.ones((block, block), dtype=np.uint8))
    noise = noise[:h, :w]

    # Make tileable by copying edges
    noise[0, :] = noise[-1, :]
    noise[:, 0] = noise[:, -1]
    return noise

def _make_color_noise(h: int, w, saturation: float = 0.8, density: float = 0.5, seed: Optional[int] = None) -> np.ndarray:
    """
    Generate tileable color noise pattern with specified saturation and density.
    Returns uint8 array [h, w, 3], RGB values
    """
    if seed is not None:
        rng = np.random.RandomState(seed)
    else:
        rng = np.random.RandomState()

    # Create density mask
    density_mask = (rng.rand(h, w) < density).astype(np.uint8)

    # Generate RGB noise
    noise = rng.randint(0, 256, (h, w, 3), dtype=np.uint8)

    # Apply density mask
    for i in range(3):
        noise[:, :, i] = noise[:, :, i] * density_mask

    # Adjust saturation using HSV color space
    hsv = cv2.cvtColor(noise, cv2.COLOR_RGB2HSV)
    hsv[:, :, 1] = hsv[:, :, 1] * saturation  # Scale saturation channel
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

    return rgb

def _make_uniform_color_noise(h: int, w, seed: Optional[int] = None) -> np.ndarray:
    """
    Generate uniform color noise pattern with same density for both foreground and background.
    Returns uint8 array [h, w, 3], RGB values
    """
    return _make_color_noise(h, w, saturation=0.85, density=0.5, seed=seed)

def _apply_gaussian_blur_mask(mask: np.ndarray, sigma: float = 1.0) -> np.ndarray:
    """
    Apply Gaussian blur to smooth the edges of the mask using OpenCV.
    """
    # Convert to uint8 and apply Gaussian blur
    mask_uint8 = (mask * 255).astype(np.uint8)
    ksize = int(6 * sigma + 1)  # Calculate kernel size
    if ksize % 2 == 0:
        ksize += 1  # Ensure odd kernel size
    blurred = cv2.GaussianBlur(mask_uint8, (ksize, ksize), sigma)
    return blurred.astype(np.float32) / 255.0

def _make_blurred_color_text_mask(w: int, h: int, text: str, font_size_ratio: float = 0.5, blur_sigma: float = 2.0) -> np.ndarray:
    """
    Render blurred binary mask for text to make edges less sharp.
    Returns uint8 array [h, w], values in {0, 1}
    """
    mask = _render_color_text_mask(w, h, text, font_size_ratio)
    # Apply Gaussian blur to soften edges
    blurred_mask = _apply_gaussian_blur_mask(mask, sigma=blur_sigma)
    return blurred_mask

def _render_color_text_mask(w: int, h: int, text: str, font_size_ratio: float = 0.5) -> np.ndarray:
    """
    Render binary mask for text using PIL (similar to _render_text_mask).
    Returns uint8 array [h, w], values in {0, 1}
    """
    font_size = int(h * font_size_ratio)
    font = _pick_font(font_size)

    img = Image.new('L', (w, h), 0)
    draw = ImageDraw.Draw(img)

    # Calculate text size and position
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (w - text_width) // 2
    y = (h - text_height) // 2

    draw.text((x, y), text, fill=255, font=font)
    mask = np.array(img, dtype=np.float32) / 255.0
    return mask

def _shift_vertical(src: np.ndarray, offset: int) -> np.ndarray:
    """
    Shift vertically with wrap (tileable). Works for both 2D and 3D arrays.
    Positive offset moves content downward.
    """
    h = src.shape[0]
    off = offset % h
    if off == 0:
        return src
    if src.ndim == 2:
        # 2D array (grayscale)
        return np.vstack([src[-off:, :], src[:-off, :]])
    elif src.ndim == 3:
        # 3D array (color), shift each channel
        return np.vstack([src[-off:, :, :], src[:-off:, :, :]])
    else:
        raise ValueError("Unsupported array dimension")

def _render_text_mask(w: int, h: int, text: str, font_size_ratio: float = 0.35) -> np.ndarray:
    """
    Render a binary mask for text centered in the frame.
    """
    font_size = int(h * font_size_ratio)
    font = _pick_font(font_size)
    img = Image.new("L", (w, h), color=0)
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = (w - tw) // 2
    y = (h - th) // 2
    draw.text((x, y), text, font=font, fill=255)
    mask = np.array(img, dtype=np.uint8)
    mask_bin = (mask > 127).astype(np.uint8)  # 1 for foreground
    return mask_bin

def _render_shape_mask(w: int, h: int, shape: str) -> np.ndarray:
    """
    Support basic shapes: 'circle', 'rectangle', 'triangle', 'heart', 'arrow'
    """
    img = Image.new("L", (w, h), color=0)
    draw = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    size = int(min(w, h) * 0.35)

    if shape == "circle":
        draw.ellipse((cx - size, cy - size, cx + size, cy + size), fill=255)
    elif shape == "rectangle":
        draw.rectangle((cx - int(size*1.2), cy - int(size*0.7), cx + int(size*1.2), cy + int(size*0.7)), fill=255)
    elif shape == "triangle":
        pts = [(cx, cy - size), (cx - size, cy + size), (cx + size, cy + size)]
        draw.polygon(pts, fill=255)
    elif shape == "heart":
        # simple heart shape
        r = size // 2
        draw.polygon([(cx, cy + size),
                      (cx - size, cy),
                      (cx, cy - r),
                      (cx + size, cy)], fill=255)
        draw.ellipse((cx - size, cy - r - r, cx, cy + r), fill=255)
        draw.ellipse((cx, cy - r - r, cx + size, cy + r), fill=255)
    elif shape == "arrow":
        shaft_w = size // 3
        draw.rectangle((cx - shaft_w//2, cy - size, cx + shaft_w//2, cy + size//2), fill=255)
        draw.polygon([(cx - size, cy - size),
                      (cx + size, cy - size),
                      (cx, cy - int(size*1.6))], fill=255)
    else:
        # default: small rectangle
        draw.rectangle((cx - size, cy - size//2, cx + size, cy + size//2), fill=255)

    mask = np.array(img, dtype=np.uint8)
    return (mask > 127).astype(np.uint8)

def _depth_mask_from_image(depth_img: np.ndarray, tl: int, tu: int) -> np.ndarray:
    """
    Create moving mask from grayscale depth image using thresholds [tl, tu].
    depth_img: uint8 [h, w]
    Return: uint8 binary mask {0,1}
    """
    d = depth_img.astype(np.uint8)
    mask = ((d >= tl) & (d <= tu)).astype(np.uint8)
    return mask

def generate_time_captcha(
    mode: str = "text",                # 'text' | 'shape' | 'depth'
    answer: Optional[str] = None,      # ground truth word/shape; required for text/shape
    depth_image: Optional[np.ndarray] = None,  # uint8 grayscale for 'depth' mode
    thresholds: Tuple[int, int] = (90, 180),
    size: Tuple[int, int] = (DEFAULT_WIDTH, DEFAULT_HEIGHT),
    fps: int = DEFAULT_FPS,
    duration_sec: float = DEFAULT_DURATION_SEC,
    speed_px_per_frame: int = DEFAULT_SPEED_PX_PER_FRAME,
    noise_block: int = DEFAULT_NOISE_BLOCK,
    noise_density: float = DEFAULT_NOISE_DENSITY,
    seed: Optional[int] = None,
) -> Tuple[bytes, str]:
    """
    Generate MP4 bytes and ground-truth string.
    """
    w, h = size
    frames_n = int(fps * duration_sec)
    rng = np.random.RandomState(seed)

    # Prepare mask M(x,y) ∈ {0,1}
    if mode == "text":
        if not answer:
            # random simple word - shorter and clearer
            answer = "".join(rng.choice(list(string.ascii_lowercase), size=rng.randint(3,5)))
        # For text mode, use larger font for better visibility
        mask = _render_text_mask(w, h, answer, font_size_ratio=0.4)
    elif mode == "shape":
        shapes = ["circle", "rectangle", "triangle", "heart", "arrow"]
        if not answer:
            answer = rng.choice(shapes)
        mask = _render_shape_mask(w, h, answer)
    elif mode == "depth":
        if depth_image is None:
            raise ValueError("depth_image is required for depth mode")
        tl, tu = thresholds
        mask = _depth_mask_from_image(depth_image, tl, tu)
        if not answer:
            answer = "object"  # generic; server-side can map to concrete label per source
    elif mode == "color_points":
        if not answer:
            # Generate 4 digits for color points mode
            answer = "".join(rng.choice(list(string.digits), size=4))
        # Use blurred mask to make edges less sharp
        mask = _make_blurred_color_text_mask(w, h, answer, font_size_ratio=0.5, blur_sigma=2.0)
    else:
        raise ValueError("Unsupported mode")

    # Generate noise patterns based on mode
    if mode == "color_points":
        # Color points mode: use uniform color noise for both foreground and background
        # Only motion difference reveals the text
        base_noise = _make_uniform_color_noise(h, w, seed=None)
        bg_noise = base_noise
        fg_noise = base_noise.copy()  # Make a copy for independent motion
    else:
        # Other modes use binary noise
        noise = _make_tiled_noise(h, w, block=noise_block, density=noise_density, seed=None)
        bg_noise = noise
        fg_noise = noise

    # Compose frames
    frames_rgb: List[np.ndarray] = []
    for t in range(frames_n):
        if mode == "color_points":
            # For color points mode, foreground moves, background static
            shifted_fg = _shift_vertical(fg_noise, offset=speed_px_per_frame * t)
            # Combine using blurred mask (convert mask to 3D)
            mask_3d = np.stack([mask] * 3, axis=2)
            frame = (mask_3d * shifted_fg + (1 - mask_3d) * bg_noise).astype(np.uint8)

            # Add random interference to make static analysis harder
            if t % 3 == 0:
                # Add occasional random pixel flips to confuse static analysis
                interference_mask = rng.random((h, w, 3)) < 0.02  # 2% random interference
                random_colors = rng.randint(0, 256, (h, w, 3), dtype=np.uint8)
                frame = np.where(interference_mask, random_colors, frame)
        else:
            # For other modes, use the original binary noise approach
            shifted = _shift_vertical(noise, offset=speed_px_per_frame * t)
            fg = shifted
            bg = noise
            frame = (mask * fg + (1 - mask) * bg).astype(np.uint8)
            # Convert to RGB
            rgb = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
            frame = rgb

        # Optional slight horizontal jitter to make replay harder
        if t % 7 == 0:
            frame = np.roll(frame, shift=rng.randint(-1, 2), axis=1)

        frames_rgb.append(frame)

    # Encode MP4 to memory (H.264 or MPEG-4)
    # Note: cv2.VideoWriter needs a path; we write to temp in memory and read back.
    tmp_path = f"/tmp/captcha_{rng.randint(1, 1_000_000)}.mp4"
    # Try different codecs for better browser compatibility
    try:
        fourcc = cv2.VideoWriter_fourcc(*"avc1")  # H.264, most compatible
    except:
        try:
            fourcc = cv2.VideoWriter_fourcc(*"x264")  # Alternative H.264
        except:
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")  # Fallback to mp4v

    writer = cv2.VideoWriter(tmp_path, fourcc, fps, (w, h))
    for fr in frames_rgb:
        writer.write(fr)
    writer.release()

    with open(tmp_path, "rb") as f:
        mp4_bytes = f.read()

    # Debug: Check if file was created successfully
    if len(mp4_bytes) == 0:
        raise ValueError("Failed to generate video file")

    print(f"Generated MP4 file size: {len(mp4_bytes)} bytes")

    try:
        os.remove(tmp_path)
    except Exception:
        pass

    return mp4_bytes, answer
