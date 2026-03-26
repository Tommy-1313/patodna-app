# gui_secure_full_no_dark.py
# -*- coding: utf-8 -*-

import streamlit as st
from pathlib import Path
import json, secrets, io, uuid, datetime, platform, time
from PIL import Image, ImageDraw
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

st.set_page_config(page_title="PatoDNA", layout="centered")
st.title("🧬PatoDNA Encode/Decode🧬")

mode = st.radio("Tryb:", ("Encode","Decode"), horizontal=True)

# =========================
# TRYB ENCODE
# =========================
if mode=="Encode":
    uploaded = st.file_uploader("Select an image", type=["jpg","jpeg","png"])
    n_codes = st.slider("How many codes do you want?",1,500,20)

    if uploaded and st.button("Encode"):
        try:
            master = generate_codes(1)[0]
            codes = generate_codes(n_codes)

            db = load_codes()
            for c in codes:
                db[c]={"status":"unused","master":master}
            save_codes(db)

            # zapisujemy obraz w pełnej rozdzielczości, ostro
            Image.open(uploaded).convert("RGB").save(TMP_INPUT)
            encode(TMP_INPUT, code=master)

            buf = io.BytesIO()
            Image.open(OUT_PATH).save(buf, format="PNG")  # ostre, brak rozmycia
            buf.seek(0)

            st.session_state.encode_done=True
            st.session_state.access_codes=codes
            st.session_state.encoded_image_bytes=buf.getvalue()

        finally:
            TMP_INPUT.unlink(missing_ok=True)

    if st.session_state.encode_done:
        st.success("✅ Encoded")
        st.code("\n".join(st.session_state.access_codes))
        # 🔹 Wyświetlamy obraz w oryginalnej rozdzielczości
        st.image(Image.open(io.BytesIO(st.session_state.encoded_image_bytes)),
                 caption="PatoDNA Product (encoded)")

        st.download_button("⬇ Download image",
            st.session_state.encoded_image_bytes,
            file_name="PatoDNA.png",
            mime="image/png")

# =========================
# TRYB DECODE
# =========================
if mode=="Decode":
    uploaded = st.file_uploader("Upload PatoDNA PNG", type=["png"])
    code = st.text_input("One-time code")

    if uploaded and code and st.button("Decode"):
        try:
            db = load_codes()
            if code not in db or db[code]["status"]=="used":
                st.error("Invalid code")
                st.stop()

            sid = get_session_id()
            master = db[code]["master"]

            with open(TMP_DNA, "wb") as f:
                f.write(uploaded.read())

            decode(
                master,
                png_path=TMP_DNA,
                watermark_text=f"CODE:{code}|SID:{sid}"
            )

            db[code] = {
                "status":"used",
                "master":master,
                "used_at":datetime.datetime.now().isoformat(),
                "session":sid,
                "platform":platform.system()
            }
            save_codes(db)

            st.success("✅ Decoded")

            # =========================
            # Animacja góra/dół z zachowaniem pełnej rozdzielczości
            # =========================
            product_img = Image.open(OUT_PATH).convert("RGB")
            recovered_img = Image.open(RECON_PATH).convert("RGB")

            w, h = recovered_img.size
            # brak resize, zachowujemy ostrość
            product_img = product_img.resize((w,h))  # tylko dopasowanie rozmiaru jeśli konieczne

            display_duration = 10
            frame_count = 1500
            delay = display_duration / frame_count / 2

            display_slot = st.empty()

            for i in range(frame_count):
                combined = Image.new("RGB", (w, h))

                osc_frac = np.sin(2 * np.pi * i / 60)
                split_top = int((h//2) * (0.5 + 0.5*osc_frac))
                split_bottom = int(h - (h//2) * (0.5 - 0.5*osc_frac))

                combined.paste(product_img.crop((0, 0, w, split_top)), (0, 0))
                combined.paste(product_img.crop((0, split_bottom, w, h)), (0, split_bottom))

                if split_bottom > split_top:
                    region = recovered_img.crop((0, split_top, w, split_bottom))
                    mask = Image.new("L", (w, split_bottom - split_top), 0)
                    draw = ImageDraw.Draw(mask)
                    radius = 6
                    draw.rounded_rectangle(
                        (0, 0, w, split_bottom - split_top),
                        radius=radius,
                        fill=255
                    )
                    combined.paste(region, (0, split_top), mask)

                # 🔹 Wyświetlamy w pełnej rozdzielczości, brak width
                display_slot.image(combined,
                                   caption="Decoded image with protection")
                time.sleep(delay)

            display_slot.empty()

        finally:
            TMP_DNA.unlink(missing_ok=True)