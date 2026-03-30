# -*- coding: utf-8 -*-
"""PatoDNA: kodowanie obrazu w obrazie z prawie niewidocznym nośnikiem."""

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

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from PIL import Image, ImageDraw, ImageFont, ImageOps
from scipy import ndimage
from scipy.interpolate import CubicSpline

plt.switch_backend("Agg")

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
PAYLOAD_DIR = BASE / "payloads"
PAYLOAD_DIR.mkdir(exist_ok=True)

CODE_LEN = 10
LSB_BITS = 2
PAYLOAD_MAGIC = b"PDNA2"
LEGACY_PAYLOAD_MAGIC = b"PDNA1"
STEGO_MAGIC = b"PDLSB"
FOOTER_MAGIC = b"PDBAR"
PAYLOAD_HEADER = struct.Struct(">5sII")
LEGACY_PAYLOAD_HEADER = struct.Struct(">5sIII")
STEGO_HEADER = struct.Struct(">5sII")
FOOTER_HEADER = struct.Struct(">5sII")
PAYLOAD_PREFIX_SIZE = PAYLOAD_HEADER.size + 16 + 32
LEGACY_PAYLOAD_PREFIX_SIZE = LEGACY_PAYLOAD_HEADER.size + 16 + 32
CARRIER_MODE_PAYLOAD = 1
CARRIER_MODE_REFERENCE = 2


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


def _capacity_for_array(image_arr: np.ndarray, bits: int = LSB_BITS) -> int:
    return (image_arr.size * bits) // 8


def _payload_path(payload_id: str) -> Path:
    safe_id = "".join(ch for ch in payload_id if ch.isalnum() or ch in "-_")
    return PAYLOAD_DIR / f"{safe_id}.bin"


def _store_payload_bytes(payload_id: str, payload_bytes: bytes) -> None:
    _payload_path(payload_id).write_bytes(payload_bytes)


def _load_payload_bytes(payload_id: str) -> bytes:
    payload_path = _payload_path(payload_id)
    if not payload_path.exists():
        raise FileNotFoundError(
            "Brak danych źródłowych na serwerze dla tego kodu."
        )
    return payload_path.read_bytes()


def _embed_bytes_in_lsb(
    image_arr: np.ndarray,
    data_bytes: bytes,
    bits: int = LSB_BITS,
) -> np.ndarray:
    flat = image_arr.reshape(-1).copy()
    capacity = (flat.size * bits) // 8
    if len(data_bytes) > capacity:
        raise ValueError("Brak miejsca na ukrycie danych w obrazie.")

    bit_mask = (1 << bits) - 1
    clear_mask = np.uint8(0xFF ^ bit_mask)
    bit_stream = np.unpackbits(np.frombuffer(data_bytes, dtype=np.uint8))

    padding = (-len(bit_stream)) % bits
    if padding:
        bit_stream = np.pad(bit_stream, (0, padding), constant_values=0)

    grouped = bit_stream.reshape(-1, bits)
    weights = 1 << np.arange(bits - 1, -1, -1, dtype=np.uint8)
    values = (grouped * weights).sum(axis=1).astype(np.uint8)

    flat[: values.size] = (flat[: values.size] & clear_mask) | values
    return flat.reshape(image_arr.shape)


def _extract_bytes_from_lsb(
    image_arr: np.ndarray,
    data_len: int,
    bits: int = LSB_BITS,
) -> bytes:
    flat = np.array(image_arr, dtype=np.uint8).reshape(-1)
    required_values = math.ceil((data_len * 8) / bits)
    if required_values > flat.size:
        raise ValueError(
            "Brak wystarczającej liczby pikseli do odczytu danych."
        )

    bit_mask = np.uint8((1 << bits) - 1)
    values = flat[:required_values] & bit_mask
    shifts = np.arange(bits - 1, -1, -1, dtype=np.uint8)
    bit_stream = ((values[:, None] >> shifts) & 1).astype(np.uint8).reshape(-1)
    packed = np.packbits(bit_stream[: data_len * 8])
    return packed.tobytes()[:data_len]


def _serialize_source_bytes(img_path, image: Image.Image):
    path = Path(img_path)
    candidates = []

    if path.exists():
        source_bytes = path.read_bytes()
        fmt = path.suffix.lstrip(".").upper() or "BIN"
        candidates.append((source_bytes, fmt.encode("ascii", errors="ignore")))

    png_buffer = io.BytesIO()
    image.save(png_buffer, format="PNG", optimize=True)
    candidates.append((png_buffer.getvalue(), b"PNG"))

    return min(candidates, key=lambda item: len(item[0]))


def _pack_payload(img_path, image: Image.Image, code: str) -> bytes:
    source_bytes, format_bytes = _serialize_source_bytes(img_path, image)
    salt = os.urandom(16)
    key = np.frombuffer(kdf_pbkdf2(salt, code), dtype=np.uint8)

    source_arr = np.frombuffer(source_bytes, dtype=np.uint8)
    encrypted = np.bitwise_xor(source_arr, np.resize(key, source_arr.size))
    checksum = hashlib.sha256(source_bytes).digest()

    header = PAYLOAD_HEADER.pack(
        PAYLOAD_MAGIC,
        len(format_bytes),
        len(source_bytes),
    )
    return header + salt + checksum + format_bytes + encrypted.tobytes()


def _unpack_payload(payload_bytes: bytes):
    magic = payload_bytes[:5]

    if magic == PAYLOAD_MAGIC:
        if len(payload_bytes) < PAYLOAD_PREFIX_SIZE:
            raise ValueError("Zakodowane dane są zbyt krótkie.")

        _, format_len, data_len = PAYLOAD_HEADER.unpack(
            payload_bytes[: PAYLOAD_HEADER.size]
        )
        offset = PAYLOAD_HEADER.size
        salt = payload_bytes[offset: offset + 16]
        checksum = payload_bytes[offset + 16: offset + 48]
        format_start = offset + 48
        format_end = format_start + format_len
        format_bytes = payload_bytes[format_start:format_end]
        encrypted = payload_bytes[format_end:]

        if len(encrypted) != data_len:
            raise ValueError("Zakodowane dane są niepełne lub uszkodzone.")

        return {
            "version": "v2",
            "format": format_bytes.decode("ascii", errors="ignore") or "PNG",
            "salt": salt,
            "checksum": checksum,
            "encrypted": encrypted,
        }

    if magic == LEGACY_PAYLOAD_MAGIC:
        if len(payload_bytes) < LEGACY_PAYLOAD_PREFIX_SIZE:
            raise ValueError("Stary format danych jest niepełny.")

        _, height, width, channels = LEGACY_PAYLOAD_HEADER.unpack(
            payload_bytes[: LEGACY_PAYLOAD_HEADER.size]
        )
        offset = LEGACY_PAYLOAD_HEADER.size
        salt = payload_bytes[offset: offset + 16]
        checksum = payload_bytes[offset + 16: offset + 48]
        encrypted = payload_bytes[offset + 48:]
        expected_len = height * width * channels

        if len(encrypted) != expected_len:
            raise ValueError("Stary format danych jest uszkodzony.")

        return {
            "version": "legacy",
            "shape": (height, width, channels),
            "salt": salt,
            "checksum": checksum,
            "encrypted": encrypted,
        }

    raise ValueError("Nieprawidłowy format danych PatoDNA.")


def _build_carrier_bytes(
    payload_bytes: bytes,
    main_capacity: int,
    payload_id: str,
) -> bytes:
    full_carrier = bytes([CARRIER_MODE_PAYLOAD]) + payload_bytes
    if len(full_carrier) <= main_capacity:
        return full_carrier

    reference_carrier = bytes([CARRIER_MODE_REFERENCE]) + payload_id.encode(
        "ascii"
    )
    if len(reference_carrier) > main_capacity:
        raise ValueError(
            "Obraz wynikowy jest zbyt mały nawet na identyfikator."
        )

    return reference_carrier


def _extract_legacy_payload_bar(image: Image.Image):
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
        raise ValueError("Ten obraz nie zawiera starego paska danych PatoDNA.")

    if bar_rows <= 0 or bar_rows >= total_rows:
        raise ValueError("Nieprawidłowa wysokość paska danych.")

    available_len = bar_rows * image_arr.shape[1] * 3
    if payload_len <= 0 or payload_len > available_len:
        raise ValueError("Nieprawidłowa długość zakodowanych danych.")

    payload_rows = image_arr[total_rows - 1 - bar_rows: total_rows - 1]
    payload_bytes = payload_rows.reshape(-1).tobytes()[:payload_len]
    visual_rows = image_arr[: total_rows - 1 - bar_rows]
    return visual_rows, payload_bytes


def _extract_payload(image: Image.Image):
    image_arr = np.array(image.convert("RGB"), dtype=np.uint8)

    try:
        header_bytes = _extract_bytes_from_lsb(image_arr, STEGO_HEADER.size)
        magic, carrier_len, _reserved = STEGO_HEADER.unpack(header_bytes)
    except (ValueError, struct.error):
        return _extract_legacy_payload_bar(image)

    if magic != STEGO_MAGIC:
        return _extract_legacy_payload_bar(image)

    carrier_bytes = _extract_bytes_from_lsb(
        image_arr,
        STEGO_HEADER.size + carrier_len,
    )[STEGO_HEADER.size:]
    return image_arr, carrier_bytes


def _resolve_payload_bytes(carrier_bytes: bytes, payload_id=None) -> bytes:
    if carrier_bytes:
        carrier_mode = carrier_bytes[0]

        if carrier_mode == CARRIER_MODE_PAYLOAD:
            return carrier_bytes[1:]

        if carrier_mode == CARRIER_MODE_REFERENCE:
            embedded_id = carrier_bytes[1:].decode("ascii", errors="ignore")
            resolved_id = payload_id or embedded_id
            return _load_payload_bytes(resolved_id)

        if carrier_bytes[:5] in (PAYLOAD_MAGIC, LEGACY_PAYLOAD_MAGIC):
            return carrier_bytes

    if payload_id:
        return _load_payload_bytes(payload_id)

    raise ValueError("Brak danych do odszyfrowania.")


def extract_visual_image(png_path=OUT_PATH) -> Image.Image:
    image = Image.open(png_path).convert("RGB")
    try:
        visual_rows, _ = _extract_payload(image)
    except (ValueError, struct.error):
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


def encode(
    img_path=IMG_PATH,
    output_png=OUT_PATH,
    code=None,
    return_payload_id=False,
):
    if code is None:
        code = generate_code()

    img = Image.open(img_path).convert("RGB")
    img_uint8 = np.array(img, dtype=np.uint8)

    visual_image = ImageOps.mirror(_build_dna_art(img_uint8))
    visual_arr = np.array(visual_image, dtype=np.uint8)
    payload_bytes = _pack_payload(img_path, img, code)
    payload_id = hashlib.sha256(payload_bytes).hexdigest()
    _store_payload_bytes(payload_id, payload_bytes)

    main_capacity = _capacity_for_array(visual_arr) - STEGO_HEADER.size
    if main_capacity <= 0:
        raise ValueError("Obraz wynikowy jest zbyt mały na dane PatoDNA.")

    carrier_bytes = _build_carrier_bytes(
        payload_bytes,
        main_capacity,
        payload_id,
    )
    header_bytes = STEGO_HEADER.pack(STEGO_MAGIC, len(carrier_bytes), 0)
    final_arr = _embed_bytes_in_lsb(visual_arr, header_bytes + carrier_bytes)
    Image.fromarray(final_arr, "RGB").save(output_png, format="PNG")

    print(f"[ENCODE] DNA-art zapisany: {output_png}")
    print(f"[KOD] {code}")

    if return_payload_id:
        return code, payload_id
    return code


def decode(
    code,
    png_path=OUT_PATH,
    out_path=RECON_PATH,
    watermark_text=None,
    payload_id=None,
):
    try:
        carrier_bytes = b""

        if png_path:
            try:
                image = Image.open(png_path)
                _, carrier_bytes = _extract_payload(image)
            except (OSError, ValueError, struct.error):
                if not payload_id:
                    raise

        payload_candidates = []
        if carrier_bytes:
            payload_candidates.append(_resolve_payload_bytes(carrier_bytes))
        if payload_id:
            payload_candidates.append(_load_payload_bytes(payload_id))

        if not payload_candidates:
            raise ValueError("Brak danych do odszyfrowania.")
    except (OSError, ValueError, struct.error, FileNotFoundError) as exc:
        print(f"[DECODE] {exc}")
        return False

    for payload_bytes in payload_candidates:
        try:
            payload = _unpack_payload(payload_bytes)
        except ValueError:
            continue

        key = np.frombuffer(kdf_pbkdf2(payload["salt"], code), dtype=np.uint8)
        encrypted_arr = np.frombuffer(payload["encrypted"], dtype=np.uint8)
        decoded = np.bitwise_xor(
            encrypted_arr,
            np.resize(key, encrypted_arr.size),
        )
        decoded_bytes = decoded.tobytes()

        if hashlib.sha256(decoded_bytes).digest() != payload["checksum"]:
            continue

        if payload["version"] == "legacy":
            out_arr = decoded.reshape(payload["shape"]).astype(np.uint8)
            out_img = Image.fromarray(out_arr, "RGB")
        else:
            out_img = Image.open(io.BytesIO(decoded_bytes)).convert("RGB")

        if watermark_text:
            out_img = add_subtle_watermark(out_img, watermark_text)

        out_img.save(out_path)
        return True

    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["encode", "decode"])
    parser.add_argument("--code")
    args = parser.parse_args()

    if args.mode == "encode":
        encode()
    else:
        ok = decode(args.code or input("Podaj 10-cyfrowy kod: "))
        message = (
            "[DECODE] Sukces"
            if ok
            else "[DECODE] Błędny kod lub uszkodzony plik"
        )
        print(message)
