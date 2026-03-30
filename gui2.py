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


def inject_mobile_styles():
    st.markdown(
        """
        <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
        }
        div.stButton > button,
        div.stDownloadButton > button {
            width: 100%;
            min-height: 3rem;
            border-radius: 14px;
            font-weight: 700;
        }
        [data-testid="stImage"] img {
            border-radius: 16px;
        }
        .mobile-save-link {
            display: block;
            width: 100%;
            box-sizing: border-box;
            text-align: center;
            padding: 0.9rem 1rem;
            margin: 0.4rem 0 0.7rem 0;
            border-radius: 14px;
            background: linear-gradient(135deg, #111827, #1f2937);
            color: white !important;
            text-decoration: none !important;
            font-weight: 700;
        }
        .mobile-tip {
            padding: 0.85rem 1rem;
            margin: 0.35rem 0 0.8rem 0;
            border-radius: 14px;
            background: #eef6ff;
            color: #0f172a;
            border: 1px solid #cfe0ff;
            font-size: 0.96rem;
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


st.set_page_config(
    page_title="PatoDNA - Secure Viewer",
    page_icon="🧬",
    layout="centered",
)
inject_mobile_styles()
st.title("🧬 PatoDNA - Secure Kodowanie/Dekodowanie")

mode = st.radio("Tryb:", ("Encode", "Decode"), horizontal=True)

if mode == "Encode":
    uploaded = st.file_uploader("Wybierz obraz", type=["jpg", "jpeg", "png"])
    n_codes = st.slider("Ile kodów?", 1, 500, 20)

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
        st.success("✅ Zakodowano")
        with st.expander("📋 Pokaż kody dostępu", expanded=True):
            st.code("\n".join(st.session_state.access_codes))

        st.image(
            normalize_for_display(st.session_state.encoded_image_bytes),
            caption="PatoDNA Product (zakodowany)",
        )
        render_mobile_tip(
            "Na iPhonie stuknij przycisk poniżej. Jeśli system nie zapisze "
            "od razu, wybierz `Zachowaj obraz` lub przytrzymaj grafikę."
        )
        render_phone_save_link(
            st.session_state.gallery_image_bytes,
            "📱 Otwórz / zapisz do Zdjęć",
        )
        st.download_button(
            "📷 Pobierz wersję do galerii (JPG)",
            st.session_state.gallery_image_bytes,
            file_name="PatoDNA_photo.jpg",
            mime="image/jpeg",
        )
        st.download_button(
            "⬇ Pobierz plik PNG",
            st.session_state.encoded_image_bytes,
            file_name="PatoDNA.png",
            mime="image/png",
        )

if mode == "Decode":
    uploaded = st.file_uploader(
        "Wgraj PatoDNA PNG (opcjonalnie)",
        type=["png", "jpg", "jpeg"],
    )
    code = st.text_input("Jednorazowy kod")

    if code and st.button("Decode"):
        try:
            db = load_codes()
            if code not in db or db[code]["status"] == "used":
                st.error("Kod nieprawidłowy lub już wykorzystany.")
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
                    "Nie udało się odszyfrować obrazu."
                    " Sprawdź plik i kod."
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

            st.success("✅ Odszyfrowano")
            recovered_img = normalize_for_display(RECON_PATH)
            recovered_buffer = io.BytesIO()
            recovered_img.save(recovered_buffer, format="JPEG", quality=95)
            st.image(
                recovered_img,
                caption="Odszyfrowany obraz z zabezpieczeniem",
            )
            render_mobile_tip(
                "Możesz od razu otworzyć odszyfrowany obraz w wersji "
                "wygodnej do zapisania w galerii telefonu."
            )
            render_phone_save_link(
                recovered_buffer.getvalue(),
                "📱 Otwórz odszyfrowany obraz do Zdjęć",
                filename="PatoDNA_decrypted.jpg",
            )
        finally:
            TMP_DNA.unlink(missing_ok=True)