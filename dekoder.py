# -*- coding: utf-8 -*-

import argparse

from pato import OUT_PATH, RECON_PATH, decode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Odtwarza obraz z pliku PatoDNA PNG z paskiem danych."
    )
    parser.add_argument(
        "--png",
        default=str(OUT_PATH),
        help="Ścieżka do zakodowanego obrazu PNG.",
    )
    parser.add_argument(
        "--out",
        default=str(RECON_PATH),
        help="Gdzie zapisać odtworzony obraz.",
    )
    parser.add_argument("--code", help="10-cyfrowy kod główny.")
    args = parser.parse_args()

    code = args.code or input("Podaj 10-cyfrowy kod: ")
    ok = decode(code, png_path=args.png, out_path=args.out)

    if ok:
        print("Obraz odtworzony:", args.out)
    else:
        print("Nie udało się odtworzyć obrazu. Kod lub plik są nieprawidłowe.")