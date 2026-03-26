import sys
import numpy as np
from PIL import Image
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA_PATH = BASE / "dna.npz"
OUTPUT_PATH = BASE / "reconstructed.png"

if not DATA_PATH.exists():
    print("Brak pliku dna.npz")
    sys.exit()

data = np.load(DATA_PATH)

encoded = data["encoded"]
feat_hash = str(data["hash"])

# ===============================
# Generowanie klucza
# ===============================
key_bytes = bytes.fromhex(feat_hash[:64])
key = np.frombuffer(key_bytes,dtype=np.uint8)

flat=encoded.flatten()

key_repeated=np.resize(key,flat.shape)

decoded=np.bitwise_xor(flat,key_repeated)
decoded=decoded.reshape(encoded.shape)

full_image = decoded/255.0

img=Image.fromarray((full_image*255).astype(np.uint8))
img.save(OUTPUT_PATH)

print("Obraz odtworzony:",OUTPUT_PATH)
img.show()