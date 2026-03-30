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


def render_phone_save_link(image_bytes, label):
    b64 = base64.b64encode(image_bytes).decode("ascii")
    st.markdown(
        (
            f'<a href="data:image/jpeg;base64,{b64}" '
            'target="_blank" rel="noopener noreferrer" '
            'style="text-decoration:none;">'
            f'<div style="display:inline-block;padding:0.6rem 0.9rem;'
            'background:#0e1117;color:white;border-radius:0.6rem;'
            f'font-weight:600;">{label}</div></a>'
        ),
        unsafe_allow_html=True,
    )


st.set_page_config(page_title="PatoDNA", layout="centered")
st.title("PatoDNA Encoding/Decoding")

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
        st.code("\n".join(st.session_state.access_codes))
        st.image(
            normalize_for_display(st.session_state.encoded_image_bytes),
            caption="PatoDNA Product",
        )
        render_phone_save_link(
            st.session_state.gallery_image_bytes,
            "📱 Open phone-gallery version",
        )
        st.caption(
            "On mobile, open the button above and choose `Save Image` "
            "to put it straight into the photo gallery."
        )
        st.download_button(
            "📷 Download gallery version (JPG)",
            st.session_state.gallery_image_bytes,
            file_name="PatoDNA_photo.jpg",
            mime="image/jpeg",
        )
        st.download_button(
            "Download PNG file",
            st.session_state.encoded_image_bytes,
            file_name="PatoDNA.png",
            mime="image/png",
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
            recovered_img = normalize_for_display(RECON_PATH)
            recovered_buffer = io.BytesIO()
            recovered_img.save(recovered_buffer, format="JPEG", quality=95)
            st.image(recovered_img, caption="Decrypted image with security")
            render_phone_save_link(
                recovered_buffer.getvalue(),
                "📱 Open decrypted image for Photos",
            )
        finally:
            TMP_DNA.unlink(missing_ok=True)