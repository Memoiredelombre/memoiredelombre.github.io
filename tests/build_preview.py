#!/usr/bin/env python3
"""
Génère une version "preview" de index.html avec le mock Supabase/Leaflet
injecté, pour pouvoir lancer les tests Playwright sans réseau ni vraie
base Supabase. Ne modifie jamais index.html : écrit un fichier à part
(preview.html, ignoré par git).

Usage :
    python3 tests/build_preview.py
    -> écrit tests/preview.html
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
INDEX = ROOT / "index.html"
STUB = pathlib.Path(__file__).resolve().parent / "mock_stub.js"
OUT = pathlib.Path(__file__).resolve().parent / "preview.html"

MARKER = '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>'


def main():
    html = INDEX.read_text(encoding="utf-8")
    stub = STUB.read_text(encoding="utf-8")
    if MARKER not in html:
        raise SystemExit(
            "build_preview.py: le marqueur d'injection (balise <script> de Leaflet) "
            "est introuvable dans index.html. L'appli a peut-être changé de CDN/version "
            "de Leaflet depuis l'écriture de ce script : mets à jour MARKER ci-dessus."
        )
    idx = html.index(MARKER) + len(MARKER)
    out = html[:idx] + "\n<script>\n" + stub + "\n</script>\n" + html[idx:]
    OUT.write_text(out, encoding="utf-8")
    print(f"OK: {OUT} ({len(out)} octets)")


if __name__ == "__main__":
    main()
