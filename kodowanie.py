# -*- coding: utf-8 -*-

import argparse

from pato import IMG_PATH, OUT_PATH, RECON_PATH, decode, encode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Koduje obraz do formatu PatoDNA, zapisując zaszyfrowane dane "
            "bezpośrednio w dolnym pasku PNG."
        )
    )
    parser.add_argument("mode", choices=["encode", "decode"])
    parser.add_argument(
        "--input",
        default=str(IMG_PATH),
        help="Ścieżka do obrazu wejściowego przy kodowaniu.",
    )
    parser.add_argument(
        "--png",
        default=str(OUT_PATH),
        help="Ścieżka do pliku PatoDNA PNG.",
    )
    parser.add_argument(
        "--output",
        default=str(RECON_PATH),
        help="Ścieżka do pliku odtworzonego przy dekodowaniu.",
    )
    parser.add_argument("--code", help="10-cyfrowy kod do dekodowania.")
    args = parser.parse_args()

    if args.mode == "encode":
        encode(img_path=args.input, output_png=args.png)
    else:
        code = args.code or input("Kod: ")
        ok = decode(code, png_path=args.png, out_path=args.output)
        print("Odtworzono:" if ok else "Dekodowanie nie powiodło się:", args.output)