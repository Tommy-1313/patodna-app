# -*- coding: utf-8 -*-
 
"""
DNA-art ENCODE/DECODE
"""
 
import io
import os
import base64
import secrets
import argparse
import hashlib
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw, ImageFont, ImageOps   # 🔐 WATERMARK + mirror
from PIL.PngImagePlugin import PngInfo
from scipy import ndimage
from scipy.interpolate import CubicSpline
from matplotlib.collections import LineCollection
import datetime, random                        # 🔐 WATERMARK
 
# ===============================
# Ścieżki
# ===============================
 
BASE = Path(__file__).resolve().parent
IMG_PATH = BASE / "poweride.jpg"
OUT_PATH = BASE / "PatoDNA_product.png"
RECON_PATH = BASE / "PatoDNA_reconstructed.png"
 
# ===============================
# Parametry
# ===============================
 
CODE_LEN = 10
B64_CHUNK_SIZE = 200_000
EMBED_PREFIX = "dna_npz_b64_"
EMBED_COUNT_KEY = "dna_npz_parts"
EMBED_SHA256_KEY = "dna_npz_sha256"
 
# ===============================
# KDF / HMAC
# ===============================
 
def generate_code():
    return "".join(str(secrets.randbelow(10)) for _ in range(CODE_LEN))
 
def kdf_pbkdf2(salt, code):
    return hashlib.pbkdf2_hmac("sha256", code.encode(), salt, 200_000, dklen=32)
 
# ===============================
# iTXt
# ===============================
 
def embed_npz_bytes_into_pnginfo(pnginfo, npz_bytes):
    b64 = base64.b64encode(npz_bytes).decode()
    parts = [b64[i:i+B64_CHUNK_SIZE] for i in range(0, len(b64), B64_CHUNK_SIZE)]
    sha = hashlib.sha256(npz_bytes).hexdigest()
    pnginfo.add_itxt(EMBED_COUNT_KEY, str(len(parts)), zip=False)
    pnginfo.add_itxt(EMBED_SHA256_KEY, sha, zip=False)
    for i, p in enumerate(parts):
        pnginfo.add_itxt(f"{EMBED_PREFIX}{i:03d}", p, zip=True)
 
def extract_npz_bytes_from_png(im: Image.Image):
    count = int(im.info[EMBED_COUNT_KEY])
    parts = [im.info[f"{EMBED_PREFIX}{i:03d}"] for i in range(count)]
    return base64.b64decode("".join(parts))
 
# ===============================
# 🔐 WATERMARK (SUBTELNY)
# ===============================
 
def add_subtle_watermark(img: Image.Image, text: str) -> Image.Image:
    img = img.convert("RGBA")
    w, h = img.size

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
    except:
        font = ImageFont.load_default()

    offset_x = random.randint(0, step_x)
    offset_y = random.randint(0, step_y)

    for y in range(offset_y, h, step_y):
        for x in range(offset_x, w, step_x):
            draw.text((x, y), stamp, fill=(255, 255, 255, alpha), font=font)

    return Image.alpha_composite(img, overlay).convert("RGB")
 
# ===============================
# ENCODE (LUSTROWE ODBICIE)
# ===============================
 
def encode(img_path=IMG_PATH, output_png=OUT_PATH, code=None):
    img = Image.open(img_path).convert("RGB")
    img_arr = np.array(img).astype(np.float32) / 255.0
    h, w, _ = img_arr.shape

    feat_hash = hashlib.sha256(img_arr.tobytes()).hexdigest()
    seed = int(feat_hash[:16], 16) % (2**31)
    np.random.seed(seed)

    num_points = 1800
    interp_x = np.random.rand(num_points)
    interp_y = np.random.rand(num_points)
    px = np.clip((interp_x * (w - 1)).astype(int), 0, w - 1)
    py = np.clip((interp_y * (h - 1)).astype(int), 0, h - 1)
    colors = img_arr[py, px]
    texts = [np.random.choice(["0", "1"]) for _ in range(num_points)]

    points = np.stack([interp_x, interp_y], axis=1)
    points_sorted = points[np.argsort(points[:, 1])]
    num_groups = 120
    group_size = max(1, len(points_sorted) // num_groups)

    y_pos, x_center, x_width = [], [], []
    for i in range(num_groups):
        start = i * group_size
        end = start + group_size if i < num_groups - 1 else len(points_sorted)
        g = points_sorted[start:end]
        y_pos.append(np.mean(g[:, 1]))
        x_center.append(np.mean(g[:, 0]))
        x_width.append(np.std(g[:, 0]))

    x_smooth = ndimage.gaussian_filter1d(x_center, sigma=2)
    width_smooth = ndimage.gaussian_filter1d(x_width, sigma=2)
    shift = width_smooth * np.sin(np.linspace(0, 4 * np.pi, len(y_pos)))

    cs_x = CubicSpline(np.arange(len(y_pos)), x_smooth + shift)
    cs_y = CubicSpline(np.arange(len(y_pos)), y_pos)
    t_fine = np.linspace(0, len(y_pos) - 1, len(y_pos) * 3)
    dna_line_x = cs_x(t_fine)
    dna_line_y = cs_y(t_fine)

    if code is None:
        code = generate_code()

    salt = os.urandom(16)
    key = np.frombuffer(kdf_pbkdf2(salt, code), dtype=np.uint8)

    img_uint8 = (img_arr * 255).astype(np.uint8)
    encoded = np.bitwise_xor(img_uint8.flatten(), np.resize(key, img_uint8.size)).reshape(img_uint8.shape)
    checksum = hashlib.sha256(img_uint8.tobytes()).hexdigest()

    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        interp_x=interp_x,
        interp_y=interp_y,
        dna_line_x=dna_line_x,
        dna_line_y=dna_line_y,
        width=w,
        height=h,
        encoded=encoded,
        hash=feat_hash,
        salt=np.frombuffer(salt, dtype=np.uint8),
        checksum=checksum,
    )

    fig, ax = plt.subplots(figsize=(w/100, h/100), dpi=100)
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")
    ax.set_axis_off()

    for xi, yi, c, t in zip(interp_x, interp_y, colors, texts):
        ax.text(xi, yi, t, fontsize=10, color=c,
                ha="center", va="center", fontweight="bold", rotation=180)

    pts = np.array([dna_line_x, dna_line_y]).T.reshape(-1, 1, 2)
    seg = np.concatenate([pts[:-1], pts[1:]], axis=1)
    ax.add_collection(LineCollection(seg, colors=(0.8, 0.2, 1.0), linewidths=3))

    buf_img = io.BytesIO()
    plt.savefig(buf_img, format="png", dpi=200, bbox_inches="tight", pad_inches=0)
    plt.close(fig)
    buf_img.seek(0)

    out_img = Image.open(buf_img).transpose(Image.ROTATE_180)

    # <-- Lustrzane odbicie poziome PatoDNA product
    out_img = ImageOps.mirror(out_img)

    pnginfo = PngInfo()
    embed_npz_bytes_into_pnginfo(pnginfo, buf.getvalue())
    out_img.save(output_png, pnginfo=pnginfo)

    print(f"[ENCODE] DNA-art zapisany: {output_png}")
    print(f"[KOD] {code}")
    return code
 
# ===============================
# DECODE + WATERMARK
# ===============================
 
def decode(code, png_path=OUT_PATH, out_path=RECON_PATH, watermark_text=None):
    im = Image.open(png_path)
    data = np.load(io.BytesIO(extract_npz_bytes_from_png(im)), allow_pickle=False)

    encoded = data["encoded"]
    salt = data["salt"].tobytes()
    checksum = data["checksum"].item()

    key = np.frombuffer(kdf_pbkdf2(salt, code), dtype=np.uint8)
    decoded = np.bitwise_xor(encoded.flatten(), np.resize(key, encoded.size)).reshape(encoded.shape)

    if hashlib.sha256(decoded.tobytes()).hexdigest() != checksum:
        return False

    out_img = Image.fromarray(decoded.astype(np.uint8))

    if watermark_text:
        out_img = add_subtle_watermark(out_img, watermark_text)

    out_img.save(out_path)
    return True
 
# ===============================
# CLI
# ===============================
 
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["encode", "decode"])
    parser.add_argument("--code")
    args = parser.parse_args()

    if args.mode == "encode":
        encode()
    else:
        decode(args.code or input("Podaj 10-cyfrowy kod: "))