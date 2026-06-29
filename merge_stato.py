#!/usr/bin/env python3
"""Unione sicura dei file di stato prima del salvataggio in cloud.

Lo stato del bot e' fatto di INSIEMI (done/visti/likati = ID commento) e di una
CODA (coda.json = ID -> risposta pronta). La fusione corretta tra la versione
locale (questo giro) e quella remota (un giro che ha gia' pushato) e' SEMPRE
l'unione: non esiste un vero "conflitto". Unendo qui, prima del commit, due giri
che si accavallano non si cancellano mai i dati a vicenda.

Uso:  python merge_stato.py <git-ref-remoto> file1.json [file2.json ...]
"""
import sys
import re
import json
import subprocess


def _versione_remota(ref, path):
    """Contenuto del file nella revisione remota (stringa vuota se assente)."""
    try:
        r = subprocess.run(["git", "show", f"{ref}:{path}"],
                           capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""
    except Exception:
        return ""


def _locale(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _ids(testo):
    return set(re.findall(r"\d+_\d+", testo or ""))


def _dict(testo):
    try:
        d = json.loads(testo)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def main():
    if len(sys.argv) < 3:
        return
    ref = sys.argv[1]
    for path in sys.argv[2:]:
        loc = _locale(path)
        rem = _versione_remota(ref, path)
        if path.endswith("coda.json"):
            # unione dei dizionari; in caso di stesso ID vince la versione locale
            unito = {**_dict(rem), **_dict(loc)}
            testo = json.dumps(unito, ensure_ascii=False, indent=0)
        else:
            unito = sorted(_ids(loc) | _ids(rem))
            testo = json.dumps(unito, ensure_ascii=False, indent=0)
        with open(path, "w", encoding="utf-8") as f:
            f.write(testo)


if __name__ == "__main__":
    main()
