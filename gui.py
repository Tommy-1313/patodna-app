# -*- coding: utf-8 -*-

import base64
import datetime
import io
import json
import platform
import secrets
import uuid
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps

from pato import OUT_PATH, RECON_PATH, decode, encode

CODES_DB = Path("codes.json")
TMP_INPUT_BASE = Path("tmp_input")
TMP_DNA = Path("tmp_dna.png")

if "encode_done" not in st.session_state:
    st.session_state.encode_done = False
    st.session_state.access_codes = []
    st.session_state.encoded_image_bytes = None
    st.session_state.gallery_image_bytes = None


def load_codes():
    if not CODES_DB.exists():
        return {}
    return json.loads(CODES_DB.read_text(encoding="utf-8"))


def save_codes(db):
    CODES_DB.write_text(json.dumps(db, indent=2), encoding="utf-8")


def generate_codes(n):
    codes = set()
    while len(codes) < n:
        codes.add("".join(str(secrets.randbelow(10)) for _ in range(10)))
    return sorted(codes)


def get_session_id():
    if "sid" not in st.session_state:
        st.session_state.sid = uuid.uuid4().hex[:12]
    return st.session_state.sid


def normalize_for_display(image_source):
    if isinstance(image_source, (bytes, bytearray)):
        image = Image.open(io.BytesIO(image_source))
    else:
        image = Image.open(image_source)
    return ImageOps.exif_transpose(image).convert("RGB")


def make_gallery_jpg(image_bytes):
    image = normalize_for_display(image_bytes)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95, optimize=True)
    return buffer.getvalue()


def render_phone_save_link(image_bytes, label, filename="PatoDNA_photo.jpg"):
    b64 = base64.b64encode(image_bytes).decode("ascii")
    st.markdown(
        (
            f'<a class="mobile-save-link" '
            f'href="data:image/jpeg;base64,{b64}" '
            f'download="{filename}">{label}</a>'
        ),
        unsafe_allow_html=True,
    )


def render_mobile_tip(text):
    st.markdown(
        f'<div class="mobile-tip">{text}</div>',
        unsafe_allow_html=True,
    )


def render_display_image(image_source, caption, protected=False):
    image = normalize_for_display(image_source)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=95, optimize=True)
    b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
    protection = (
        "pointer-events:none;-webkit-user-select:none;user-select:none;"
        "-webkit-touch-callout:none;"
        if protected
        else ""
    )
    st.markdown(
        (
            '<div class="image-card">'
            f'<img src="data:image/jpeg;base64,{b64}" '
            f'alt="{caption}" style="{protection}">'
            f'<div class="image-caption">{caption}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )
    return buffer.getvalue()


def render_hero_card(title, subtitle):
    st.markdown(
        (
            '<div class="hero-card">'
            f'<div class="hero-title">{title}</div>'
            f'<div class="hero-subtitle">{subtitle}</div>'
            '</div>'
        ),
        unsafe_allow_html=True,
    )


def inject_mobile_styles():
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(
                    circle at top left,
                    rgba(168, 85, 247, 0.22),
                    transparent 0 28%
                ),
                radial-gradient(
                    circle at top right,
                    rgba(126, 34, 206, 0.18),
                    transparent 0 24%
                ),
                linear-gradient(160deg, #020204 0%, #09030f 45%, #14051f 100%);
            color: #faf5ff;
        }
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 760px;
        }
        h1, h2, h3, label, .stMarkdown, .stText {
            color: #f5ebff !important;
        }
        .hero-card {
            padding: 1rem 1.1rem;
            margin: 0.35rem 0 1rem 0;
            border-radius: 18px;
            border: 1px solid rgba(192, 132, 252, 0.22);
            background: linear-gradient(
                135deg,
                rgba(28, 6, 43, 0.96),
                rgba(5, 5, 10, 0.94)
            );
            box-shadow: 0 12px 30px rgba(91, 33, 182, 0.28);
        }
        .hero-title {
            font-size: 1.08rem;
            font-weight: 800;
            color: #f5d0fe;
            margin-bottom: 0.25rem;
        }
        .hero-subtitle {
            font-size: 0.94rem;
            line-height: 1.45;
            color: #ddd6fe;
        }
        div.stButton > button,
        div.stDownloadButton > button {
            width: 100%;
            min-height: 3rem;
            border-radius: 14px;
            font-weight: 800;
            border: 1px solid rgba(216, 180, 254, 0.24);
            background: linear-gradient(135deg, #581c87, #7e22ce);
            color: white;
            box-shadow: 0 10px 24px rgba(88, 28, 135, 0.38);
        }
        div.stButton > button:hover,
        div.stDownloadButton > button:hover {
            border-color: rgba(243, 232, 255, 0.38);
            background: linear-gradient(135deg, #6b21a8, #9333ea);
            color: white;
        }
        .stTextInput > div > div > input,
        .stNumberInput input {
            background: rgba(20, 12, 33, 0.92) !important;
            color: #f5ebff !important;
            border: 1px solid rgba(196, 181, 253, 0.18) !important;
            border-radius: 12px !important;
        }
        .stFileUploader {
            padding: 0.35rem;
            border-radius: 16px;
            background: rgba(18, 10, 30, 0.72);
            border: 1px solid rgba(196, 181, 253, 0.14);
        }
        div[data-baseweb="select"],
        div[role="radiogroup"] {
            background: rgba(18, 10, 30, 0.62);
            padding: 0.25rem;
            border-radius: 14px;
        }
        .stSlider {
            padding-top: 0.4rem;
        }
        .stExpander {
            border: 1px solid rgba(196, 181, 253, 0.14) !important;
            border-radius: 16px !important;
            background: rgba(14, 8, 24, 0.88) !important;
        }
        [data-testid="stImage"] img {
            border-radius: 18px;
            border: 1px solid rgba(196, 181, 253, 0.16);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
        }
        .image-card {
            margin: 0.5rem 0 1rem 0;
            border-radius: 18px;
            overflow: hidden;
            background: rgba(12, 7, 18, 0.92);
            border: 1px solid rgba(196, 181, 253, 0.16);
            box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
        }
        .image-card img {
            display: block;
            width: 100%;
            height: auto;
        }
        .image-caption {
            padding: 0.75rem 0.9rem 0.85rem 0.9rem;
            text-align: center;
            color: #ddd6fe;
            font-size: 0.95rem;
        }
        .mobile-save-link {
            display: block;
            width: 100%;
            box-sizing: border-box;
            text-align: center;
            padding: 0.95rem 1rem;
            margin: 0.4rem 0 0.7rem 0;
            border-radius: 14px;
            background: linear-gradient(135deg, #3b0764, #7e22ce);
            color: white !important;
            text-decoration: none !important;
            font-weight: 800;
            box-shadow: 0 10px 24px rgba(76, 29, 149, 0.34);
        }
        .mobile-tip {
            padding: 0.85rem 1rem;
            margin: 0.35rem 0 0.8rem 0;
            border-radius: 14px;
            background: rgba(88, 28, 135, 0.22);
            color: #f5e9ff;
            border: 1px solid rgba(216, 180, 254, 0.22);
            font-size: 0.96rem;
        }
        div[data-testid="stSuccess"] {
            background: rgba(34, 197, 94, 0.14) !important;
            color: #dcfce7 !important;
            border: 1px solid rgba(74, 222, 128, 0.25) !important;
            border-radius: 14px;
        }
        div[data-testid="stError"] {
            background: rgba(239, 68, 68, 0.14) !important;
            border-radius: 14px;
        }
        @media (max-width: 768px) {
            .block-container {
                padding-left: 0.85rem;
                padding-right: 0.85rem;
                padding-top: 0.7rem;
            }
            h1 {
                font-size: 1.45rem !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="PatoDNA", page_icon="🧬", layout="centered")
inject_mobile_styles()
st.title("PatoDNA Encoding/Decoding")
render_hero_card(
    "Dark Violet Edition",
    (
        "A cleaner purple-black experience with modern cards, gradients "
        "and mobile-friendly actions."
    ),
)

mode = st.radio("Tryb:", ("Encode", "Decode"), horizontal=True)

if mode == "Encode":
    uploaded = st.file_uploader("Select an image", type=["jpg", "jpeg", "png"])
    n_codes = st.slider("How many codes do you want?", 1, 500, 20)

    if uploaded and st.button("Encode"):
        try:
            master = generate_codes(1)[0]
            codes = generate_codes(n_codes)

            suffix = Path(uploaded.name or "upload.png").suffix or ".png"
            tmp_input = TMP_INPUT_BASE.with_suffix(suffix.lower())
            tmp_input.write_bytes(uploaded.getvalue())
            _, payload_id = encode(
                tmp_input,
                code=master,
                return_payload_id=True,
            )

            image_bytes = OUT_PATH.read_bytes()
            gallery_bytes = make_gallery_jpg(image_bytes)

            db = load_codes()
            for one_time_code in codes:
                db[one_time_code] = {
                    "status": "unused",
                    "master": master,
                    "payload_id": payload_id,
                }
            save_codes(db)

            st.session_state.encode_done = True
            st.session_state.access_codes = codes
            st.session_state.encoded_image_bytes = image_bytes
            st.session_state.gallery_image_bytes = gallery_bytes
        finally:
            if "tmp_input" in locals():
                tmp_input.unlink(missing_ok=True)

    if st.session_state.encode_done:
        st.success("✅ Encoded")
        with st.expander("📋 Show access codes", expanded=True):
            st.code("\n".join(st.session_state.access_codes))

        render_display_image(
            st.session_state.encoded_image_bytes,
            "PatoDNA Product",
        )
        render_mobile_tip(
            "There is now only one save option below for the encoded image."
        )
        render_phone_save_link(
            st.session_state.gallery_image_bytes,
            "📱 Save encoded image",
        )

if mode == "Decode":
    uploaded = st.file_uploader(
        "Upload PatoDNA (optional)",
        type=["png", "jpg", "jpeg"],
    )
    code = st.text_input("One-time code")

    if code and st.button("Decode"):
        try:
            db = load_codes()
            if code not in db or db[code]["status"] == "used":
                st.error("Code invalid or already used.")
                st.stop()

            sid = get_session_id()
            master = db[code]["master"]
            payload_id = db[code].get("payload_id")
            png_path = None

            if uploaded is not None:
                with open(TMP_DNA, "wb") as file_obj:
                    file_obj.write(uploaded.read())
                png_path = TMP_DNA

            decode_ok = decode(
                master,
                png_path=png_path,
                payload_id=payload_id,
                watermark_text=f"CODE:{code}|SID:{sid}",
            )
            if not decode_ok:
                st.error(
                    "Could not decrypt the image."
                    " Check the file and code."
                )
                st.stop()

            db[code] = {
                "status": "used",
                "master": master,
                "used_at": datetime.datetime.now().isoformat(),
                "session": sid,
                "platform": platform.system(),
            }
            save_codes(db)

            st.success("✅ Decrypted")
            render_display_image(
                RECON_PATH,
                "Decrypted image with security",
                protected=True,
            )
            render_mobile_tip(
                "The decrypted image is preview-only. Full screenshot blocking "
                "is not technically possible in a browser."
            )
        finally:
            TMP_DNA.unlink(missing_ok=True)