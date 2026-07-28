"""benchmark_locale.py - il modello locale puo' sostituire Claude sulla classificazione?

Test set: proposte.csv, che contiene i commenti reali GIA' classificati da Claude.
Quelle categorie sono il riferimento: non "la verita' assoluta", ma cio' che il bot
fa oggi in produzione. La domanda e' se un modello gratuito in locale prende le
stesse decisioni.

Il SYSTEM_PROMPT viene IMPORTATO da reply_bot, non ricopiato: se il prompt cambia,
il benchmark misura ancora la cosa giusta.

USO:
    py benchmark_locale.py                    # fnv-copy, 20 per categoria, batch 20
    py benchmark_locale.py fnv-copy 20 5      # batch da 5 commenti
    py benchmark_locale.py fnv-copy 20 1      # un commento per chiamata

Sul batch: in produzione vale 20 perche' con Claude ogni chiamata ripaga gli 859
token di system prompt. In locale il costo e' tempo, non denaro, quindi conviene
scendere: piu' chiamate, ognuna con meno commenti da tenere allineati.
"""

import csv
import json
import random
import sys
import time
import urllib.request
from collections import Counter, defaultdict

from reply_bot import BATCH_SCHEMA, SYSTEM_PROMPT

MODELLO = sys.argv[1] if len(sys.argv) > 1 else "fnv-copy"
PER_CATEGORIA = int(sys.argv[2]) if len(sys.argv) > 2 else 20
BATCH = int(sys.argv[3]) if len(sys.argv) > 3 else 20
URL = "http://localhost:11434/api/chat"

CATEGORIE = ["sostenitore", "critico", "neutro", "volgare", "spam"]
# Scambiare un critico o un volgare per un sostenitore significa pubblicare un
# ringraziamento sotto un attacco. E' l'unico errore che non si puo' assorbire.
GRAVI = {("critico", "sostenitore"), ("volgare", "sostenitore"), ("spam", "sostenitore")}


def carica_campione():
    """Campione stratificato: stesso numero di commenti per categoria, cosi' le
    categorie rare (spam, neutro) non spariscono dentro la maggioranza sostenitore."""
    per_cat = defaultdict(list)
    with open("proposte.csv", encoding="utf-8") as f:
        for riga in csv.DictReader(f):
            testo = (riga.get("commento") or "").strip()
            cat = (riga.get("categoria") or "").strip()
            if testo and cat in CATEGORIE:
                per_cat[cat].append({"autore": riga.get("autore", ""), "testo": testo, "atteso": cat})

    rng = random.Random(20260728)  # seed fisso: due esecuzioni confrontabili
    campione = []
    for cat in CATEGORIE:
        voci = per_cat[cat]
        rng.shuffle(voci)
        campione.extend(voci[:PER_CATEGORIA])
        if len(voci) < PER_CATEGORIA:
            print(f"  nota: solo {len(voci)} commenti disponibili per '{cat}'")
    rng.shuffle(campione)  # mescola: niente blocchi omogenei che aiutino il modello
    return campione


def classifica(chunk):
    """Stessa costruzione del prompt di reply_bot.classifica_batch."""
    righe = []
    for i, it in enumerate(chunk, 1):
        nome = (it["autore"] or "").strip() or "(nessun nome disponibile)"
        righe.append(f'[{i}] Nome: {nome} | Commento: "{it["testo"]}"')
    contenuto = "Ecco i commenti da classificare:\n\n" + "\n".join(righe)

    corpo = json.dumps({
        "model": MODELLO,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": contenuto},
        ],
        "stream": False,
        "format": BATCH_SCHEMA,   # Ollama accetta lo schema JSON per l'output strutturato
        "options": {"temperature": 0.3},
    }).encode("utf-8")

    req = urllib.request.Request(URL, data=corpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        risposta = json.loads(r.read().decode("utf-8"))

    dati = json.loads(risposta["message"]["content"])
    out = {}
    for v in dati.get("risultati", []):
        n = v.get("n")
        if isinstance(n, int) and 1 <= n <= len(chunk):
            out[n - 1] = v
    return out, risposta.get("eval_count", 0), risposta.get("eval_duration", 1) / 1e9


def main():
    campione = carica_campione()
    print(f"modello   : {MODELLO}")
    print(f"campione  : {len(campione)} commenti ({PER_CATEGORIA} per categoria)")
    print(f"batch     : {BATCH} commenti per chiamata\n")

    matrice = Counter()   # (atteso, ottenuto) -> conteggio
    mancanti = 0
    token_tot = 0
    secondi_tot = 0.0
    esempi_gravi = []

    for i in range(0, len(campione), BATCH):
        chunk = campione[i:i + BATCH]
        t0 = time.time()
        try:
            esiti, tok, sec = classifica(chunk)
        except Exception as e:
            print(f"  batch {i // BATCH + 1}: ERRORE {e}")
            mancanti += len(chunk)
            continue
        token_tot += tok
        secondi_tot += sec

        for j, it in enumerate(chunk):
            v = esiti.get(j)
            if not v:
                mancanti += 1
                continue
            ottenuto = v.get("categoria", "?")
            matrice[(it["atteso"], ottenuto)] += 1
            if (it["atteso"], ottenuto) in GRAVI and len(esempi_gravi) < 8:
                esempi_gravi.append((it["atteso"], ottenuto, it["testo"][:90]))

        print(f"  batch {i // BATCH + 1}/{(len(campione) + BATCH - 1) // BATCH} "
              f"({time.time() - t0:.0f}s)")

    totale = sum(matrice.values())
    if not totale:
        print("\nNessun risultato utilizzabile.")
        return

    esatti = sum(c for (a, o), c in matrice.items() if a == o)
    print(f"\n{'=' * 66}")
    print(f"ACCORDO CON CLAUDE : {esatti}/{totale}  ({100 * esatti / totale:.1f}%)")
    if mancanti:
        print(f"non classificati   : {mancanti}")
    if secondi_tot:
        print(f"velocita'          : {token_tot / secondi_tot:.1f} token/s")

    print(f"\n{'atteso (Claude)':<16} -> ottenuto (locale)")
    for atteso in CATEGORIE:
        riga = [(o, c) for (a, o), c in matrice.items() if a == atteso]
        n = sum(c for _, c in riga)
        if not n:
            continue
        ok = sum(c for o, c in riga if o == atteso)
        dettaglio = "  ".join(f"{o}:{c}" for o, c in sorted(riga, key=lambda x: -x[1]))
        print(f"{atteso:<16} {ok}/{n} ({100 * ok / n:.0f}%)   {dettaglio}")

    gravi = sum(c for k, c in matrice.items() if k in GRAVI)
    print(f"\nERRORI GRAVI (critico/volgare/spam letti come sostenitore): {gravi}/{totale}"
          f"  ({100 * gravi / totale:.1f}%)")
    print("  -> ogni caso e' un ringraziamento pubblicato sotto un attacco.")
    for atteso, ottenuto, testo in esempi_gravi:
        print(f'   [{atteso} -> {ottenuto}] "{testo}"')


if __name__ == "__main__":
    main()
