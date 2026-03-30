# -*- coding: utf-8 -*-

import datetime
import io
import json
import platform
import secrets
import uuid
from pathlib import Path

import streamlit as st
from PIL import Image

from pato import OUT_PATH, RECON_PATH, decode, encode

CODES_DB = Path("codes.json")
TMP_INPUT_BASE = Path("tmp_input")
TMP_DNA = Path("tmp_dna.png")

if "encode_done" not in st.session_state:
    st.session_state.encode_done = False
    st.session_state.access_codes = []
    st.session_state.encoded_image_bytes = None


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


st.set_page_config(page_title="PatoDNA - Secure Viewer", layout="centered")
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
            encode(tmp_input, code=master)

            image_bytes = OUT_PATH.read_bytes()

            db = load_codes()
            for one_time_code in codes:
                db[one_time_code] = {"status": "unused", "master": master}
            save_codes(db)

            st.session_state.encode_done = True
            st.session_state.access_codes = codes
            st.session_state.encoded_image_bytes = image_bytes
        finally:
            if "tmp_input" in locals():
                tmp_input.unlink(missing_ok=True)

    if st.session_state.encode_done:
        st.success("✅ Zakodowano")
        st.code("\n".join(st.session_state.access_codes))
        st.image(
            Image.open(io.BytesIO(st.session_state.encoded_image_bytes)),
            caption="PatoDNA Product (zakodowany)",
        )
        st.download_button(
            "⬇ Pobierz obraz",
            st.session_state.encoded_image_bytes,
            file_name="PatoDNA.png",
            mime="image/png",
        )

if mode == "Decode":
    uploaded = st.file_uploader("Wgraj PatoDNA PNG", type=["png"])
    code = st.text_input("Jednorazowy kod")

    if uploaded and code and st.button("Decode"):
        try:
            db = load_codes()
            if code not in db or db[code]["status"] == "used":
                st.error("Kod nieprawidłowy lub już wykorzystany.")
                st.stop()

            sid = get_session_id()
            master = db[code]["master"]

            with open(TMP_DNA, "wb") as file_obj:
                file_obj.write(uploaded.read())

            decode_ok = decode(
                master,
                png_path=TMP_DNA,
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
            recovered_img = Image.open(RECON_PATH).convert("RGB")
            st.image(
                recovered_img,
                caption="Odszyfrowany obraz z zabezpieczeniem",
            )
        finally:
            TMP_DNA.unlink(missing_ok=True)