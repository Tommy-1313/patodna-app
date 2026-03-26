# -*- coding: utf-8 -*-

import io
import os
import base64
import secrets
import argparse
import hashlib
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image
from PIL.PngImagePlugin import PngInfo


# ===============================
# ŚCIEŻKI
# ===============================

BASE = Path(__file__).resolve().parent

IMG_PATH = BASE / "poweride.jpg"
OUT_PATH = BASE / "poweride_dna.png"
RECON_PATH = BASE / "reconstructed.png"


# ===============================
# PARAMETRY
# ===============================

CODE_LEN = 10
CHUNK = 200_000


# ===============================
# KDF
# ===============================

def generate_code():
    return "".join(str(secrets.randbelow(10)) for _ in range(CODE_LEN))


def kdf(salt, code):
    return hashlib.pbkdf2_hmac(
        "sha256",
        code.encode(),
        salt,
        200_000,
        dklen=32
    )


# ===============================
# iTXt
# ===============================

def embed(pnginfo, data):
    b64 = base64.b64encode(data).decode()

    parts = [b64[i:i+CHUNK] for i in range(0, len(b64), CHUNK)]

    pnginfo.add_itxt("parts", str(len(parts)))

    for i, p in enumerate(parts):
        pnginfo.add_itxt(f"p{i:03d}", p, zip=True)


def extract(im):
    count = int(im.info["parts"])

    parts = []
    for i in range(count):
        parts.append(im.info[f"p{i:03d}"])

    return base64.b64decode("".join(parts))


# ===============================
# ENCODE
# ===============================

def encode():

    img = Image.open(IMG_PATH).convert("RGB")
    arr = np.array(img).astype(np.uint8)

    # 🔐 kod
    code = generate_code()
    salt = os.urandom(16)

    key = np.frombuffer(kdf(salt, code), dtype=np.uint8)

    flat = arr.flatten()
    key_rep = np.resize(key, flat.shape)

    encoded = np.bitwise_xor(flat, key_rep).reshape(arr.shape)

    # 💾 pakowanie
    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        encoded=encoded,
        salt=np.frombuffer(salt, dtype=np.uint8)
    )
    data = buf.getvalue()

    # ===============================
    # 🎨 DNA-ART (wizualna zmiana)
    # ===============================

    h, w, _ = arr.shape

    fig, ax = plt.subplots(figsize=(w/100, h/100), dpi=100)

    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")
    ax.set_axis_off()

    np.random.seed(0)

    xs = np.random.rand(2000)
    ys = np.random.rand(2000)

    colors = arr[
        (ys*(h-1)).astype(int),
        (xs*(w-1)).astype(int)
    ] / 255.0

    for x, y, c in zip(xs, ys, colors):
        ax.text(
            x, y,
            np.random.choice(["0", "1"]),
            color=c,
            fontsize=8,
            ha="center",
            va="center"
        )

    buf_img = io.BytesIO()

    plt.savefig(
        buf_img,
        format="png",
        dpi=200,
        bbox_inches="tight",
        pad_inches=0,
        facecolor="black"
    )

    plt.close(fig)
    buf_img.seek(0)

    out_img = Image.open(buf_img)

    # ===============================
    # 🔐 embed do PNG
    # ===============================

    pnginfo = PngInfo()
    embed(pnginfo, data)

    out_img.save(OUT_PATH, pnginfo=pnginfo)

    print("\n🔐 KOD:", code)
    print("Zapisano:", OUT_PATH)


# ===============================
# DECODE
# ===============================

def decode(code):

    im = Image.open(OUT_PATH)

    data = np.load(io.BytesIO(extract(im)))

    encoded = data["encoded"]
    salt = data["salt"].tobytes()

    key = np.frombuffer(kdf(salt, code), dtype=np.uint8)

    flat = encoded.flatten()
    key_rep = np.resize(key, flat.shape)

    decoded = np.bitwise_xor(flat, key_rep).reshape(encoded.shape)

    Image.fromarray(decoded.astype(np.uint8)).save(RECON_PATH)

    print("Odtworzono:", RECON_PATH)


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
        decode(args.code or input("Kod: "))