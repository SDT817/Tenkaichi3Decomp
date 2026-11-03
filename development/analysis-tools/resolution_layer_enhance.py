"""Offline menu-art proposal: reconstruct native outline/fill coverage at 4x.

For the five selected menu labels, the native art blends a constant outline
colour with a solid or vertical-gradient fill. Estimate that fill per source row,
separate its coverage, and enlarge the two antialiased contours independently.
This reduces muddy colour transitions while retaining the source letter shapes.
It is intentionally a preview, not a general-purpose game texture converter.
"""
from collections import Counter
import numpy as np
from PIL import Image, ImageFilter

SCALE = 4


def upsample_mask(mask):
    image = Image.fromarray(np.uint8(np.clip(mask, 0, 1) * 255), 'L')
    image = image.resize((image.width * SCALE, image.height * SCALE), Image.Resampling.BICUBIC)
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    values = np.asarray(image, dtype=np.float64) / 255
    values = np.clip((values - 0.29) / 0.42, 0, 1)
    return values * values * (3 - 2 * values)


def enhance_layers(image):
    rgba = np.asarray(image, dtype=np.float64)
    rgb, alpha = rgba[:, :, :3], rgba[:, :, 3] / 255
    opaque = [tuple(map(int, px)) for px in rgba.reshape(-1, 4) if px[3] == 255]
    assert opaque, 'These samples require an opaque native outline.'
    outline = np.asarray(Counter(opaque).most_common(1)[0][0][:3], dtype=np.float64)
    distances = np.linalg.norm(rgb - outline, axis=2)
    distances[alpha < 0.99] = 0
    rows = np.arange(image.height)
    farthest = np.argmax(distances, axis=1)
    fill = rgb[rows, farthest].copy()
    valid = np.max(distances, axis=1) > 40
    assert np.any(valid)
    for channel in range(3):
        fill[:, channel] = np.interp(rows, rows[valid], fill[valid, channel])
    direction = fill[:, None, :] - outline
    denominator = np.maximum(np.sum(direction**2, axis=2), 1)
    coverage = np.sum((rgb - outline) * direction, axis=2) / denominator
    coverage = np.clip(coverage, 0, 1) * (alpha > 0.99)
    outer, inner = upsample_mask(alpha), upsample_mask(coverage)
    height, width = outer.shape
    fill_large = np.stack([np.interp((np.arange(height) + 0.5) / SCALE - 0.5, rows, fill[:, c])
                           for c in range(3)], axis=1)
    color = outline[None, None, :] * (1 - inner[:, :, None]) + fill_large[:, None, :] * inner[:, :, None]
    result = np.concatenate([color, outer[:, :, None] * 255], axis=2)
    assert width == image.width * SCALE and height == image.height * SCALE
    return Image.fromarray(np.uint8(np.clip(np.rint(result), 0, 255)), 'RGBA')
