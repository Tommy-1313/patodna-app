# gui_secure_full_no_dark.py
# -*- coding: utf-8 -*-

import streamlit as st
from pathlib import Path
import json, secrets, io, uuid, datetime, platform
from PIL import Image
import numpy as np
from pato import encode, decode, OUT_PATH, RECON_PATH

CODES_DB = Path("codes.json")
TMP_INPUT = Path("tmp_input.png")
TMP_DNA = Path("tmp_dna.png")

if "encode_done" not in st.session_state:
    st.session_state.encode_done = False
    st.session_state.access_codes = []
    st.session_state.encoded_image_bytes = None

def load_codes():
    if not CODES_DB.exists():
        return {}
    return json.loads(CODES_DB.read_text())

def save_codes(db):
    CODES_DB.write_text(json.dumps(db, indent=2))

def generate_codes(n):
    s=set()
    while len(s)<n:
        s.add("".join(str(secrets.randbelow(10)) for _ in range(10)))
    return sorted(s)

def get_session_id():
    if "sid" not in st.session_state:
        st.session_state.sid = uuid.uuid4().hex[:12]
    return st.session_state.sid

st.set_page_config(page_title="PatoDNA - Secure Viewer", layout="centered")
st.title("🧬 PatoDNA - Secure Kodowanie/Dekodowanie")

mode = st.radio("Tryb:", ("Encode","Decode"), horizontal=True)

# =========================
# TRYB ENCODE
# =========================
if mode=="Encode":
    uploaded = st.file_uploader("Wybierz obraz", type=["jpg","jpeg","png"])
    n_codes = st.slider("Ile kodów?",1,500,20)

    if uploaded and st.button("Encode"):
        try:
            master = generate_codes(1)[0]
            codes = generate_codes(n_codes)

            db = load_codes()
            for c in codes:
                db[c]={"status":"unused","master":master}
            save_codes(db)

            Image.open(uploaded).convert("RGB").save(TMP_INPUT)
            encode(TMP_INPUT, code=master)

            buf = io.BytesIO()
            encoded_img = Image.open(OUT_PATH)
            encoded_img.save(buf, format="PNG")
            buf.seek(0)

            st.session_state.encode_done=True
            st.session_state.access_codes=codes
            st.session_state.encoded_image_bytes=buf.getvalue()

        finally:
            TMP_INPUT.unlink(missing_ok=True)

    if st.session_state.encode_done:
        st.success("✅ Zakodowano")
        st.code("\n".join(st.session_state.access_codes))
        st.image(Image.open(io.BytesIO(st.session_state.encoded_image_bytes)),
                 caption="PatoDNA Product (zakodowany)", width=400)
        st.download_button("⬇ Pobierz obraz",
            st.session_state.encoded_image_bytes,
            file_name="PatoDNA.png",
            mime="image/png")

# =========================
# TRYB DECODE - proste wyświetlanie odkodowanego obrazu
# =========================
if mode=="Decode":
    uploaded = st.file_uploader("Wgraj PatoDNA PNG", type=["png"])
    code = st.text_input("Jednorazowy kod")

    if uploaded and code and st.button("Decode"):
        try:
            db = load_codes()
            if code not in db or db[code]["status"]=="used":
                st.error("Kod nieprawidłowy")
                st.stop()

            sid = get_session_id()
            master = db[code]["master"]

            # zapisanie wgranej grafiki tymczasowo
            with open(TMP_DNA, "wb") as f:
                f.write(uploaded.read())

            # odszyfrowanie
            decode(
                master,
                png_path=TMP_DNA,
                watermark_text=f"CODE:{code}|SID:{sid}"
            )

            # aktualizacja statusu kodu
            db[code] = {
                "status":"used",
                "master":master,
                "used_at":datetime.datetime.now().isoformat(),
                "session":sid,
                "platform":platform.system()
            }
            save_codes(db)

            st.success("✅ Odszyfrowano")

            # wyświetlenie odkodowanego obrazu (pełny rozmiar, ostry)
            recovered_img = Image.open(RECON_PATH).convert("RGB")
            st.image(recovered_img, caption="Odszyfrowany obraz", use_column_width=False)

        finally:
            TMP_DNA.unlink(missing_ok=True)