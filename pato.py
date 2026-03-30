# -*- coding: utf-8 -*-
"""PatoDNA: kodowanie obrazu w obrazie z paskiem danych na dole."""

import argparse
import datetime
import hashlib
import io
import math
import os
import random
import secrets
import struct
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage
from scipy.interpolate import CubicSpline


BASE = Path(__file__).resolve().parent
DEFAULT_INPUTS = (
    "poweridee.jpg",
    "poweride.jpg",
    "poweridee.png",
    "poweride.png",
)
IMG_PATH = next(
    ((BASE / name) for name in DEFAULT_INPUTS if (BASE / name).exists()),
    BASE / "poweridee.jpg",
)
OUT_PATH = BASE / "PatoDNA_product.png"
RECON_PATH = BASE / "PatoDNA_reconstructed.png"

CODE_LEN = 10
PAYLOAD_MAGIC = b"PDNA1"
FOOTER_MAGIC = b"PDBAR"
PAYLOAD_HEADER = struct.Struct(">5sIII")
FOOTER_HEADER = struct.Struct(">5sII")
PAYLOAD_PREFIX_SIZE = PAYLOAD_HEADER.size + 16 + 32


def generate_code() -> str:
    return "".join(str(secrets.randbelow(10)) for _ in range(CODE_LEN))


def kdf_pbkdf2(salt: bytes, code: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        code.encode("utf-8"),
        salt,
        200_000,
        dklen=32,
    )


def _pack_payload(img_uint8: np.ndarray, code: str) -> bytes:
    height, width, channels = img_uint8.shape
    salt = os.urandom(16)
    key = np.frombuffer(kdf_pbkdf2(salt, code), dtype=np.uint8)

    flat = img_uint8.reshape(-1)
    encrypted = np.bitwise_xor(flat, np.resize(key, flat.size))
    checksum = hashlib.sha256(flat.tobytes()).digest()

    header = PAYLOAD_HEADER.pack(PAYLOAD_MAGIC, height, width, channels)
    return header + salt + checksum + encrypted.tobytes()


def _unpack_payload(payload_bytes: bytes):
    if len(payload_bytes) < PAYLOAD_PREFIX_SIZE:
        raise ValueError("Zakodowany pasek danych jest zbyt krótki.")

    magic, height, width, channels = PAYLOAD_HEADER.unpack(
        payload_bytes[: PAYLOAD_HEADER.size]
    )
    if magic != PAYLOAD_MAGIC:
        raise ValueError("Nieprawidłowy format danych PatoDNA.")

    offset = PAYLOAD_HEADER.size
    salt = payload_bytes[offset: offset + 16]
    checksum = payload_bytes[offset + 16: offset + 48]
    encrypted = payload_bytes[offset + 48:]

    expected_len = height * width * channels
    if len(encrypted) != expected_len:
        raise ValueError("Pasek danych jest uszkodzony lub niepełny.")

    return height, width, channels, salt, checksum, encrypted


def _append_payload_bar(
    image: Image.Image,
    payload_bytes: bytes,
) -> Image.Image:
    image_arr = np.array(image.convert("RGB"), dtype=np.uint8)
    _, width, _ = image_arr.shape
    capacity_per_row = width * 3

    if capacity_per_row <= 0:
        raise ValueError(
            "Nie można zapisać danych w obrazie o zerowej szerokości."
        )

    bar_rows = max(1, math.ceil(len(payload_bytes) / capacity_per_row))
    padded_len = bar_rows * capacity_per_row
    padded_payload = payload_bytes.ljust(padded_len, b"\x00")

    data_bar = np.frombuffer(padded_payload, dtype=np.uint8).reshape(
        bar_rows, width, 3
    )

    footer = np.zeros((1, width, 3), dtype=np.uint8)
    footer_bytes = FOOTER_HEADER.pack(
        FOOTER_MAGIC,
        bar_rows,
        len(payload_bytes),
    )
    footer.reshape(-1)[: len(footer_bytes)] = np.frombuffer(
        footer_bytes,
        dtype=np.uint8,
    )

    combined = np.vstack([image_arr, data_bar, footer])
    return Image.fromarray(combined.astype(np.uint8), "RGB")


def _extract_payload_bar(image: Image.Image):
    image_arr = np.array(image.convert("RGB"), dtype=np.uint8)
    total_rows = image_arr.shape[0]

    if total_rows < 2:
        raise ValueError("Obraz jest zbyt mały, aby zawierać pasek danych.")

    footer_bytes = image_arr[-1].reshape(-1).tobytes()
    if len(footer_bytes) < FOOTER_HEADER.size:
        raise ValueError("Brak stopki PatoDNA.")

    magic, bar_rows, payload_len = FOOTER_HEADER.unpack(
        footer_bytes[: FOOTER_HEADER.size]
    )
    if magic != FOOTER_MAGIC:
        raise ValueError("Ten obraz nie zawiera paska danych PatoDNA.")

    if bar_rows <= 0 or bar_rows >= total_rows:
        raise ValueError("Nieprawidłowa wysokość paska danych.")

    available_len = bar_rows * image_arr.shape[1] * 3
    if payload_len <= 0 or payload_len > available_len:
        raise ValueError("Nieprawidłowa długość zakodowanych danych.")

    payload_rows = image_arr[total_rows - 1 - bar_rows: total_rows - 1]
    payload_bytes = payload_rows.reshape(-1).tobytes()[:payload_len]
    visual_rows = image_arr[: total_rows - 1 - bar_rows]

    return visual_rows, payload_bytes


def extract_visual_image(png_path=OUT_PATH) -> Image.Image:
    image = Image.open(png_path).convert("RGB")
    try:
        visual_rows, _ = _extract_payload_bar(image)
    except ValueError:
        return image

    return Image.fromarray(visual_rows.astype(np.uint8), "RGB")


def add_subtle_watermark(img: Image.Image, text: str) -> Image.Image:
    img = img.convert("RGBA")
    width, height = img.size

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    stamp = f"{text} | {timestamp}"

    alpha = 18
    font_size = 13
    step_x = 420
    step_y = 280

    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        font = ImageFont.load_default()

    offset_x = random.randint(0, step_x)
    offset_y = random.randint(0, step_y)

    for y in range(offset_y, height, step_y):
        for x in range(offset_x, width, step_x):
            draw.text((x, y), stamp, fill=(255, 255, 255, alpha), font=font)

    return Image.alpha_composite(img, overlay).convert("RGB")


def _build_dna_art(img_uint8: np.ndarray) -> Image.Image:
    img_arr = img_uint8.astype(np.float32) / 255.0
    height, width, _ = img_arr.shape

    feat_hash = hashlib.sha256(img_arr.tobytes()).hexdigest()
    seed = int(feat_hash[:16], 16) % (2**31)
    rng = np.random.default_rng(seed)

    num_points = 1800
    interp_x = rng.random(num_points)
    interp_y = rng.random(num_points)
    px = np.clip((interp_x * (width - 1)).astype(int), 0, width - 1)
    py = np.clip((interp_y * (height - 1)).astype(int), 0, height - 1)
    colors = img_arr[py, px]
    texts = rng.choice(["0", "1"], size=num_points)

    points = np.stack([interp_x, interp_y], axis=1)
    points_sorted = points[np.argsort(points[:, 1])]
    num_groups = 120
    group_size = max(1, len(points_sorted) // num_groups)

    y_pos = []
    x_center = []
    x_width = []
    for i in range(num_groups):
        start = i * group_size
        end = start + group_size if i < num_groups - 1 else len(points_sorted)
        group = points_sorted[start:end]
        y_pos.append(np.mean(group[:, 1]))
        x_center.append(np.mean(group[:, 0]))
        x_width.append(np.std(group[:, 0]))

    x_smooth = ndimage.gaussian_filter1d(x_center, sigma=2)
    width_smooth = ndimage.gaussian_filter1d(x_width, sigma=2)
    shift = width_smooth * np.sin(np.linspace(0, 4 * np.pi, len(y_pos)))

    spline_x = CubicSpline(np.arange(len(y_pos)), x_smooth + shift)
    spline_y = CubicSpline(np.arange(len(y_pos)), y_pos)
    t_fine = np.linspace(0, len(y_pos) - 1, len(y_pos) * 3)
    dna_line_x = spline_x(t_fine)
    dna_line_y = spline_y(t_fine)

    fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")
    ax.set_axis_off()

    for x_val, y_val, color, char in zip(interp_x, interp_y, colors, texts):
        ax.text(
            x_val,
            y_val,
            char,
            fontsize=10,
            color=color,
            ha="center",
            va="center",
            fontweight="bold",
            rotation=180,
        )

    points_line = np.array([dna_line_x, dna_line_y]).T.reshape(-1, 1, 2)
    segments = np.concatenate([points_line[:-1], points_line[1:]], axis=1)
    ax.add_collection(
        LineCollection(segments, colors=(0.8, 0.2, 1.0), linewidths=3)
    )

    buffer = io.BytesIO()
    plt.savefig(
        buffer,
        format="png",
        dpi=200,
        bbox_inches="tight",
        pad_inches=0,
    )
    plt.close(fig)
    buffer.seek(0)

    return Image.open(buffer).convert("RGB").transpose(Image.ROTATE_180)


def encode(img_path=IMG_PATH, output_png=OUT_PATH, code=None):
    if code is None:
        code = generate_code()

    img = Image.open(img_path).convert("RGB")
    img_uint8 = np.array(img, dtype=np.uint8)

    visual_image = ImageOps.mirror(_build_dna_art(img_uint8))
    payload_bytes = _pack_payload(img_uint8, code)
    final_image = _append_payload_bar(visual_image, payload_bytes)
    final_image.save(output_png, format="PNG")

    print(f"[ENCODE] DNA-art zapisany: {output_png}")
    print(f"[KOD] {code}")
    return code


def decode(code, png_path=OUT_PATH, out_path=RECON_PATH, watermark_text=None):
    try:
        image = Image.open(png_path)
        _, payload_bytes = _extract_payload_bar(image)
        height, width, channels, salt, checksum, encrypted = _unpack_payload(
            payload_bytes
        )
    except (OSError, ValueError, struct.error) as exc:
        print(f"[DECODE] {exc}")
        return False

    key = np.frombuffer(kdf_pbkdf2(salt, code), dtype=np.uint8)
    encrypted_arr = np.frombuffer(encrypted, dtype=np.uint8)
    decoded = np.bitwise_xor(encrypted_arr, np.resize(key, encrypted_arr.size))

    if hashlib.sha256(decoded.tobytes()).digest() != checksum:
        return False

    out_arr = decoded.reshape((height, width, channels)).astype(np.uint8)
    out_img = Image.fromarray(out_arr, "RGB")

    if watermark_text:
        out_img = add_subtle_watermark(out_img, watermark_text)

    out_img.save(out_path)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["encode", "decode"])
    parser.add_argument("--code")
    args = parser.parse_args()

    if args.mode == "encode":
        encode()
    else:
        ok = decode(args.code or input("Podaj 10-cyfrowy kod: "))
        print("[DECODE] Sukces" if ok else "[DECODE] Błędny kod lub uszkodzony plik")