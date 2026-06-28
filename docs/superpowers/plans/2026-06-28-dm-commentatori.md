# DM ai commentatori (Private Reply) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Aggiungere uno script `dm_bot.py` che invia un DM (Private Reply) di ringraziamento + invito a seguire/like ai commentatori dei post della Pagina, con cap anti-ban e modalità prova/live/test-uno.

**Architecture:** Script Python a sé, separato dal bot commenti rodato. Importa le funzioni Graph e di fetch già esistenti da `reply_bot.py` (nessuna duplicazione). Nessun uso di Claude: i messaggi sono 10 template a rotazione con il nome. Logica pura (selezione candidati, rotazione testo, conteggio cap) isolata e testata; l'invio reale è dietro un confine sottile e verificato dal vivo.

**Tech Stack:** Python 3.14, `requests` (via helper di reply_bot.py), `python-dotenv`, Graph API v21.0 endpoint `/{comment_id}/private_replies`. Test in Python puro (niente pytest), runnable con `python test_dm_bot.py`.

**Riferimento spec:** `docs/superpowers/specs/2026-06-28-dm-commentatori-design.md`

---

## File Structure

- **Create:** `dm_bot.py` — script principale (CLI, selezione, invio, stato).
- **Create:** `test_dm_bot.py` — test in Python puro per le funzioni pure.
- **Create (a runtime, versionato):** `dm_inviati.json` — `{autore_id: "YYYY-MM-DD"}`.
- **Create (a runtime, output prova):** `dm_proposte.csv`.
- **Modify:** `DOCUMENTAZIONE.md` — nuova sezione "DM ai commentatori".
- **Riuso (no modifica prevista):** `reply_bot.py` — import di `graph_post`, `get_comments`, `get_posts`, `get_page_info`, `estrai_post_id`.

Convenzione test: `test_dm_bot.py` contiene funzioni `test_*` e, in fondo, un runner che le esegue tutte stampando PASS/FAIL ed esce con codice ≠ 0 se qualcosa fallisce. Ogni task aggiunge i suoi test a questo file.

---

## Task 0: Verifica che reply_bot.py sia importabile senza effetti collaterali

**Files:**
- Inspect: `reply_bot.py`

- [ ] **Step 1: Verifica il guard `__main__`**

Conferma che `reply_bot.py` esegua `main()` solo sotto `if __name__ == "__main__":` (riga ~654) e che `graph_post`, `get_comments`, `get_posts`, `get_page_info`, `estrai_post_id` siano definite a livello di modulo.

- [ ] **Step 2: Prova l'import a vuoto**

Run: `python -c "import reply_bot; print(reply_bot.GRAPH); print('ok')"`
Expected: stampa l'URL Graph e `ok`, senza eseguire il bot e senza errori.

---

## Task 1: `nome_breve()` — estrazione del nome di battesimo

**Files:**
- Create: `dm_bot.py`
- Create: `test_dm_bot.py`

- [ ] **Step 1: Scrivi il test che fallisce**

In `test_dm_bot.py`:

```python
import dm_bot


def test_nome_breve_estrae_il_primo_nome():
    assert dm_bot.nome_breve("Mario Rossi") == "Mario"
    assert dm_bot.nome_breve("Anna") == "Anna"
    assert dm_bot.nome_breve("  Luca   Bianchi ") == "Luca"
    assert dm_bot.nome_breve("") == ""
    assert dm_bot.nome_breve(None) == ""
    assert dm_bot.nome_breve("   ") == ""


# --- runner (resta in fondo al file; i test successivi vanno PRIMA di questo blocco) ---
def _run():
    import sys
    falliti = 0
    for nome, fn in sorted(globals().items()):
        if nome.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {nome}")
            except AssertionError as e:
                falliti += 1
                print(f"FAIL {nome}: {e}")
            except Exception as e:
                falliti += 1
                print(f"ERRORE {nome}: {e!r}")
    print(f"\n{falliti} test falliti")
    sys.exit(1 if falliti else 0)


if __name__ == "__main__":
    _run()
```

- [ ] **Step 2: Esegui il test e verifica che fallisca**

Run: `python test_dm_bot.py`
Expected: `ERRORE test_nome_breve_...: ModuleNotFoundError` o `AttributeError` (dm_bot/nome_breve non esiste).

- [ ] **Step 3: Crea `dm_bot.py` con l'intestazione e `nome_breve()`**

```python
#!/usr/bin/env python3
"""
dm_bot.py — invia un DM (Private Reply) ai commentatori dei post della Pagina.

Separato da reply_bot.py (bot commenti) di proposito: e' un'azione ad alto rischio
(un DM non si ritira), va accesa/spenta in modo indipendente. Riusa le funzioni Graph
e di fetch di reply_bot.py. NON usa Claude: i testi sono template a rotazione.

Modalita':
  python dm_bot.py --ultimi-post 5                 # PROVA: scrive dm_proposte.csv, non invia
  python dm_bot.py --post <URL|ID> --live --test-uno  # invia UN solo DM e si ferma
  python dm_bot.py --ultimi-post 5 --live --max-giorno 20

Vincolo Meta: la Private Reply raggiunge SOLO chi ha commentato, una volta per commento,
e richiede il permesso pages_messaging (verso il pubblico generico serve Accesso Avanzato).
"""

import argparse
import csv
import json
import os
import random
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from reply_bot import (
    graph_post,
    get_comments,
    get_posts,
    get_page_info,
    estrai_post_id,
)

# --- Config ---
DM_INVIATI_FILE = "dm_inviati.json"
DM_CSV = "dm_proposte.csv"
MAX_GIORNO_DEFAULT = 150
PAUSA_MIN = 30      # secondi tra un DM e l'altro (piu' lente dei commenti)
PAUSA_MAX = 70


def nome_breve(autore_nome):
    """Primo nome di battesimo da 'Mario Rossi' -> 'Mario'. Stringa vuota se assente."""
    if not autore_nome:
        return ""
    parti = autore_nome.strip().split()
    return parti[0] if parti else ""
```

- [ ] **Step 4: Esegui il test e verifica che passi**

Run: `python test_dm_bot.py`
Expected: `PASS test_nome_breve_estrae_il_primo_nome` e `0 test falliti`.

- [ ] **Step 5: Commit**

```bash
git add dm_bot.py test_dm_bot.py
git commit -m "feat(dm): scheletro dm_bot.py + nome_breve con test"
```

---

## Task 2: `DM_TEMPLATES` + `componi_dm()` con fallback nome assente

**Files:**
- Modify: `dm_bot.py`
- Modify: `test_dm_bot.py`

- [ ] **Step 1: Scrivi i test che falliscono**

In `test_dm_bot.py`, PRIMA del blocco runner:

```python
def test_componi_dm_con_nome_sostituisce_il_segnaposto():
    t = dm_bot.componi_dm(0, "Marco")
    assert "{nome}" not in t
    assert "Marco" in t


def test_componi_dm_ruota_sui_10_template():
    # idx 0 e idx 10 devono dare lo stesso template (rotazione modulo 10)
    assert dm_bot.componi_dm(0, "Marco") == dm_bot.componi_dm(10, "Marco")
    assert len(dm_bot.DM_TEMPLATES) == 10


def test_componi_dm_senza_nome_resta_pulito():
    # nessun template, senza nome, deve contenere segnaposto o spazi/virgole orfane
    for i in range(len(dm_bot.DM_TEMPLATES)):
        t = dm_bot.componi_dm(i, "")
        assert "{nome}" not in t, f"segnaposto residuo nel template {i}: {t}"
        assert " ," not in t and " ." not in t, f"punteggiatura orfana nel template {i}: {t}"
        assert "  " not in t, f"doppio spazio nel template {i}: {t}"
        assert t[0].isupper(), f"iniziale minuscola nel template {i}: {t}"


def test_componi_dm_casi_specifici_senza_nome():
    # template 0: "Ciao {nome}, ho letto..." -> "Ciao, ho letto..."
    assert dm_bot.componi_dm(0, "").startswith("Ciao, ho letto")
    # template 1: "{nome}, grazie per esserci..." -> "Grazie per esserci..."
    assert dm_bot.componi_dm(1, "").startswith("Grazie per esserci")
    # template 8 (idx): "Grazie {nome}. Una community..." -> "Grazie. Una community..."
    assert dm_bot.componi_dm(8, "").startswith("Grazie. Una community")
    # template 9 (idx): "Contento di averti qui, {nome}. Se vuoi..." -> "...qui. Se vuoi..."
    assert dm_bot.componi_dm(9, "").startswith("Contento di averti qui. Se vuoi")
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `python test_dm_bot.py`
Expected: FAIL/ERRORE sui nuovi test (`componi_dm`/`DM_TEMPLATES` non esistono).

- [ ] **Step 3: Aggiungi template e funzione a `dm_bot.py`**

Dopo `nome_breve`:

```python
# 10 template a rotazione, neutri e community-oriented. Una sola emoji per messaggio;
# 🇮🇹 distribuito "di tanto in tanto" (template idx 2, 6, 8).
DM_TEMPLATES = [
    "Ciao {nome}, ho letto il tuo commento e mi ha fatto piacere davvero. Siamo in tanti a pensarla così, e più siamo più le nostre idee girano. Se non lo fai già, segui la pagina e lasciale un like: ti aspetto di là 💪",
    "{nome}, grazie per esserci. Questa pagina la portiamo avanti insieme, un commento alla volta. Mettile un like e premi \"Segui\": così non ti perdi niente e diamo più voce a quello in cui crediamo 🙏",
    "Senti {nome}, gente come te è esattamente il motivo per cui vale la pena continuare. Aiutami a far crescere la community: un like alla pagina, il tasto Segui, e fai girare il messaggio a chi la pensa come noi. Conta parecchio 🇮🇹",
    "Il tuo sostegno non passa inosservato, {nome}. Qui dentro siamo una squadra: più follower vuol dire più persone raggiunte e più idee che viaggiano. Se ti va, segui la pagina e mettile un like 👊",
    "{nome}, due secondi: se condividi quello che scrivo, restami vicino. Segui la pagina e lasciale un mi piace. Più siamo, più diventa difficile ignorarci. E a me serve proprio questo.",
    "Grazie del commento, {nome}. Lo dico sul serio: ogni persona che si unisce rende questa voce più forte. Premi Segui, metti like alla pagina, e se conosci qualcuno che la pensa come noi tiralo dentro. Le idee si diffondono così.",
    "Ciao {nome}, mi piace quando arrivano commenti come il tuo. Vuol dire che non sono solo. Tienimi d'occhio: segui la pagina e mettile un like, così restiamo in contatto e portiamo avanti insieme le nostre battaglie 🇮🇹",
    "{nome}, te lo chiedo diretto: seguimi sulla pagina e lasciale un like. Non è una formalità, è quello che ci fa crescere e ci permette di far sentire la nostra di campana. Sei già dei nostri, tanto vale renderlo ufficiale 😉",
    "Grazie {nome}. Una community vera si costruisce con le persone che ci mettono la faccia nei commenti, come hai fatto tu. Aiutami: like alla pagina, tasto Segui, e condividi quando qualcosa ti convince. Insieme arriviamo lontano 🇮🇹",
    "Contento di averti qui, {nome}. Se vuoi che queste idee continuino a girare, il modo più semplice è restare connessi: segui la pagina, mettile un like, e ogni tanto fai girare un post. Ci conto su di te 💪",
]


def componi_dm(contatore, nome):
    """Sceglie un template a rotazione e inserisce il nome. Se il nome manca, rimuove il
    segnaposto lasciando una frase naturale e pulita."""
    t = DM_TEMPLATES[contatore % len(DM_TEMPLATES)]
    if nome:
        return t.replace("{nome}", nome)
    # Nome assente: sostituzioni ordinate (le piu' specifiche prima).
    t = t.replace("Ciao {nome}, ", "Ciao, ")
    t = t.replace("Senti {nome}, ", "Senti, ")
    t = t.replace(", {nome}.", ".")   # nome a fine frase
    t = t.replace(" {nome}.", ".")    # "Grazie {nome}." -> "Grazie."
    t = t.replace("{nome}, ", "")     # nome a inizio frase
    t = t.replace("{nome}", "")       # residui
    t = t.strip()
    if t:
        t = t[0].upper() + t[1:]
    return t
```

- [ ] **Step 4: Esegui e verifica il successo**

Run: `python test_dm_bot.py`
Expected: tutti `PASS`, `0 test falliti`.

- [ ] **Step 5: Commit**

```bash
git add dm_bot.py test_dm_bot.py
git commit -m "feat(dm): 10 template a rotazione + componi_dm con fallback nome"
```

---

## Task 3: Stato `dm_inviati.json` — carica/salva + `conta_dm_oggi()`

**Files:**
- Modify: `dm_bot.py`
- Modify: `test_dm_bot.py`

- [ ] **Step 1: Scrivi i test che falliscono**

In `test_dm_bot.py`, prima del runner:

```python
def test_conta_dm_oggi_conta_solo_la_data_di_oggi():
    stato = {"a": "2026-06-28", "b": "2026-06-28", "c": "2026-06-27"}
    assert dm_bot.conta_dm_oggi(stato, "2026-06-28") == 2
    assert dm_bot.conta_dm_oggi(stato, "2026-06-27") == 1
    assert dm_bot.conta_dm_oggi({}, "2026-06-28") == 0


def test_carica_e_salva_dm_inviati(tmp_path_helper=None):
    import os
    path = "dm_inviati_test_tmp.json"
    try:
        dm_bot.salva_dm_inviati({"x": "2026-06-28"}, path)
        ricaricato = dm_bot.carica_dm_inviati(path)
        assert ricaricato == {"x": "2026-06-28"}
        # file mancante -> dict vuoto
        assert dm_bot.carica_dm_inviati("non_esiste_xyz.json") == {}
    finally:
        if os.path.exists(path):
            os.remove(path)
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `python test_dm_bot.py`
Expected: FAIL/ERRORE sui nuovi test.

- [ ] **Step 3: Aggiungi le funzioni a `dm_bot.py`**

```python
def carica_dm_inviati(path=DM_INVIATI_FILE):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def salva_dm_inviati(stato, path=DM_INVIATI_FILE):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(stato, f, ensure_ascii=False, indent=0)


def conta_dm_oggi(stato, oggi):
    return sum(1 for data in stato.values() if data == oggi)
```

- [ ] **Step 4: Esegui e verifica il successo**

Run: `python test_dm_bot.py`
Expected: tutti `PASS`.

- [ ] **Step 5: Commit**

```bash
git add dm_bot.py test_dm_bot.py
git commit -m "feat(dm): stato dm_inviati.json (carica/salva) + conta_dm_oggi"
```

---

## Task 4: `seleziona_candidati()` — filtro destinatari

**Files:**
- Modify: `dm_bot.py`
- Modify: `test_dm_bot.py`

- [ ] **Step 1: Scrivi i test che falliscono**

In `test_dm_bot.py`:

```python
def _commento(cid, autore_id, nome="Tizio", message="bel post"):
    return {"id": cid, "autore_id": autore_id, "autore_nome": nome,
            "message": message, "gia_risposto_pagina": False}


def test_seleziona_candidati_filtra_e_deduplica():
    page_id = "PAGE"
    commenti = [
        _commento("c1", "u1"),                       # ok
        _commento("c2", "u1"),                       # stesso autore -> scartato (dedup)
        _commento("c3", "PAGE"),                     # commento della Pagina -> scartato
        _commento("c4", "u2", message="   "),        # vuoto -> scartato
        _commento("c5", "u3"),                       # ok
        _commento("c6", ""),                         # senza autore_id -> scartato
    ]
    dm_inviati = {"u3": "2026-06-28"}                # u3 gia' DM oggi -> scartato
    cand = dm_bot.seleziona_candidati(commenti, page_id, dm_inviati, "2026-06-28")
    ids = [c["autore_id"] for c in cand]
    assert ids == ["u1"]                             # solo u1 sopravvive
    assert cand[0]["comment_id"] == "c1"
    assert cand[0]["nome"] == "Tizio"


def test_seleziona_candidati_ammette_se_dm_in_altra_data():
    commenti = [_commento("c1", "u1")]
    dm_inviati = {"u1": "2026-06-27"}                # ieri -> oggi puo' ricevere
    cand = dm_bot.seleziona_candidati(commenti, "PAGE", dm_inviati, "2026-06-28")
    assert len(cand) == 1
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `python test_dm_bot.py`
Expected: FAIL/ERRORE.

- [ ] **Step 3: Aggiungi la funzione a `dm_bot.py`**

```python
def seleziona_candidati(commenti, page_id, dm_inviati, oggi):
    """Da una lista di commenti (formato get_comments) ricava i destinatari DM:
    salta vuoti, la Pagina stessa, chi ha gia' un DM oggi; deduplica per autore_id."""
    visti_giro = set()
    out = []
    for c in commenti:
        autore_id = c.get("autore_id") or ""
        msg = (c.get("message") or "").strip()
        if not msg:
            continue
        if not autore_id or autore_id == page_id:
            continue
        if dm_inviati.get(autore_id) == oggi:
            continue
        if autore_id in visti_giro:
            continue
        visti_giro.add(autore_id)
        out.append({
            "comment_id": c["id"],
            "autore_id": autore_id,
            "nome": nome_breve(c.get("autore_nome", "")),
        })
    return out
```

- [ ] **Step 4: Esegui e verifica il successo**

Run: `python test_dm_bot.py`
Expected: tutti `PASS`.

- [ ] **Step 5: Commit**

```bash
git add dm_bot.py test_dm_bot.py
git commit -m "feat(dm): seleziona_candidati con filtro Pagina/vuoti/cap-giornaliero e dedup"
```

---

## Task 5: `private_reply()` — chiamata Graph all'endpoint giusto

**Files:**
- Modify: `dm_bot.py`
- Modify: `test_dm_bot.py`

- [ ] **Step 1: Scrivi il test che fallisce (monkeypatch di graph_post)**

In `test_dm_bot.py`:

```python
def test_private_reply_chiama_endpoint_corretto():
    chiamate = {}

    def fake_graph_post(path, token, data):
        chiamate["path"] = path
        chiamate["token"] = token
        chiamate["data"] = data
        return {"id": "mid_1"}

    originale = dm_bot.graph_post
    dm_bot.graph_post = fake_graph_post
    try:
        res = dm_bot.private_reply("TOK", "504760203329428_999", "ciao a tutti")
    finally:
        dm_bot.graph_post = originale

    assert chiamate["path"] == "504760203329428_999/private_replies"
    assert chiamate["token"] == "TOK"
    assert chiamate["data"] == {"message": "ciao a tutti"}
    assert res == {"id": "mid_1"}
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `python test_dm_bot.py`
Expected: ERRORE (`private_reply` non esiste).

- [ ] **Step 3: Aggiungi la funzione a `dm_bot.py`**

```python
def private_reply(token, comment_id, testo):
    """Invia un messaggio privato (DM) in risposta a un commento.
    Endpoint Meta: POST /{comment_id}/private_replies con message=...
    Usa il graph_post di reply_bot.py (retry/backoff sugli errori temporanei inclusi)."""
    return graph_post(f"{comment_id}/private_replies", token, {"message": testo})
```

- [ ] **Step 4: Esegui e verifica il successo**

Run: `python test_dm_bot.py`
Expected: tutti `PASS`.

- [ ] **Step 5: Commit**

```bash
git add dm_bot.py test_dm_bot.py
git commit -m "feat(dm): private_reply verso /{comment_id}/private_replies"
```

---

## Task 6: Helper orario + raccolta candidati per post + modalità PROVA (CSV) + CLI

**Files:**
- Modify: `dm_bot.py`
- Modify: `test_dm_bot.py`

- [ ] **Step 1: Scrivi i test che falliscono (orario + oggi)**

In `test_dm_bot.py`:

```python
def test_e_fascia_notturna():
    assert dm_bot.e_fascia_notturna(2) is True
    assert dm_bot.e_fascia_notturna(5) is True
    assert dm_bot.e_fascia_notturna(6) is False
    assert dm_bot.e_fascia_notturna(14) is False
    assert dm_bot.e_fascia_notturna(23) is False


def test_oggi_str_formato_iso():
    s = dm_bot.oggi_str()
    # formato YYYY-MM-DD
    assert len(s) == 10 and s[4] == "-" and s[7] == "-"
```

- [ ] **Step 2: Esegui e verifica il fallimento**

Run: `python test_dm_bot.py`
Expected: ERRORE (`e_fascia_notturna`/`oggi_str` non esistono).

- [ ] **Step 3: Aggiungi helper, raccolta, PROVA e `main()` a `dm_bot.py`**

```python
def e_fascia_notturna(ora_it):
    """True tra le 00 e le 06 (escluse) ora italiana: di notte non si invia."""
    return ora_it < 6


def oggi_str():
    """Data odierna 'YYYY-MM-DD' in fuso Europe/Rome (fallback UTC+2)."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Rome")).strftime("%Y-%m-%d")
    except Exception:
        from datetime import datetime, timezone, timedelta
        return datetime.now(timezone(timedelta(hours=2))).strftime("%Y-%m-%d")


def ora_italiana():
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Rome")).hour
    except Exception:
        from datetime import datetime, timezone, timedelta
        return datetime.now(timezone(timedelta(hours=2))).hour


def raccogli_candidati(token, page_id, post_ids, dm_inviati, oggi):
    """Scorre i post indicati, raccoglie i commenti e applica seleziona_candidati.
    Deduplica anche TRA post diversi (una persona = un solo candidato per giro)."""
    tutti = []
    visti_globali = set()
    for pid in post_ids:
        commenti = get_comments(token, pid, page_id)
        print(f"  post {pid}: {len(commenti)} commenti")
        for cand in seleziona_candidati(commenti, page_id, dm_inviati, oggi):
            if cand["autore_id"] in visti_globali:
                continue
            visti_globali.add(cand["autore_id"])
            cand["post_id"] = pid
            tutti.append(cand)
    return tutti


def scrivi_prova_csv(candidati):
    with open(DM_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["post_id", "comment_id", "autore_id", "nome", "dm_proposto"])
        for i, c in enumerate(candidati):
            w.writerow([c.get("post_id", ""), c["comment_id"], c["autore_id"],
                        c["nome"], componi_dm(i, c["nome"])])
    print(f"  scritte {len(candidati)} proposte in {DM_CSV}")


def invia_dm(token, candidati, dm_inviati, oggi, max_giorno, max_per_post, solo_uno=False):
    """Invia i DM con pause, cap globale giornaliero, kill-switch a 3 errori di fila.
    Salva lo stato dopo OGNI invio (idempotenza)."""
    inviati_oggi = conta_dm_oggi(dm_inviati, oggi)
    n = 0
    errori = 0
    for i, cand in enumerate(candidati):
        if inviati_oggi >= max_giorno:
            print(f"  Tetto giornaliero {max_giorno} raggiunto: stop.")
            break
        if max_per_post and n >= max_per_post:
            print(f"  Tetto per sessione {max_per_post} raggiunto: stop.")
            break
        testo = componi_dm(i, cand["nome"])
        try:
            private_reply(token, cand["comment_id"], testo)
            dm_inviati[cand["autore_id"]] = oggi
            salva_dm_inviati(dm_inviati)
            inviati_oggi += 1
            n += 1
            errori = 0
            etichetta = cand["nome"] or "(senza nome)"
            print(f"  [DM] {etichetta}: {testo}")
        except Exception as e:
            errori += 1
            print(f"  [errore DM su {cand['comment_id']}] {e}")
            if errori >= 3:
                print("  STOP: 3 errori di fila (permesso pages_messaging? blocco Meta?).")
                break
            continue
        if solo_uno:
            print("  --test-uno: inviato 1 DM, mi fermo.")
            break
        pausa = random.uniform(PAUSA_MIN, PAUSA_MAX)
        print(f"    ...pausa {pausa:.0f}s")
        time.sleep(pausa)
    return n


def main():
    ap = argparse.ArgumentParser(description="Invia DM (Private Reply) ai commentatori")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--post", help="ID o URL del post")
    g.add_argument("--ultimi-post", type=int, metavar="N", help="ultimi N post della pagina")
    ap.add_argument("--live", action="store_true", help="invia davvero (senza: solo PROVA->CSV)")
    ap.add_argument("--test-uno", action="store_true", help="in --live, invia UN solo DM e stop")
    ap.add_argument("--max-giorno", type=int, default=MAX_GIORNO_DEFAULT,
                    help=f"tetto globale giornaliero di DM (default {MAX_GIORNO_DEFAULT})")
    ap.add_argument("--max", type=int, default=None, metavar="N",
                    help="tetto di DM per questa sessione")
    args = ap.parse_args()

    if args.live and e_fascia_notturna(ora_italiana()):
        print(f"Ora italiana ~{ora_italiana()}:00 — fascia notturna (00-06): nessun invio.")
        return

    token = os.environ.get("FB_PAGE_TOKEN")
    if not token:
        print("Manca FB_PAGE_TOKEN (.env). Vedi README.md")
        sys.exit(1)

    page_id, page_name = get_page_info(token)
    print(f"Pagina: {page_name} (id {page_id})")
    print(f"Modalita': {'LIVE - invia' if args.live else 'PROVA - solo dm_proposte.csv'}")

    if args.post:
        post_ids = [estrai_post_id(args.post, page_id)]
    else:
        post_ids = [p["id"] for p in get_posts(token, page_id, args.ultimi_post)]
    print(f"{len(post_ids)} post da scandire")

    oggi = oggi_str()
    dm_inviati = carica_dm_inviati()
    print(f"  DM gia' inviati oggi ({oggi}): {conta_dm_oggi(dm_inviati, oggi)}")

    candidati = raccogli_candidati(token, page_id, post_ids, dm_inviati, oggi)
    print(f"  candidati DM (dopo filtri e dedup): {len(candidati)}")

    if not args.live:
        scrivi_prova_csv(candidati)
        print(f"\nPROVA completata. Controlla {DM_CSV}. Per inviare: aggiungi --live")
        return

    n = invia_dm(token, candidati, dm_inviati, oggi, args.max_giorno, args.max,
                 solo_uno=args.test_uno)
    print(f"\nDM inviati in questa sessione: {n}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Esegui i test unitari**

Run: `python test_dm_bot.py`
Expected: tutti `PASS`, `0 test falliti`.

- [ ] **Step 5: Smoke test della CLI in PROVA (senza token reale)**

Run: `python dm_bot.py --ultimi-post 5`
Expected: se `FB_PAGE_TOKEN` non è nel `.env`, stampa `Manca FB_PAGE_TOKEN` ed esce. Se il `.env` c'è, scrive `dm_proposte.csv` **senza inviare nulla**. In entrambi i casi: nessuna eccezione Python.

- [ ] **Step 6: Commit**

```bash
git add dm_bot.py test_dm_bot.py
git commit -m "feat(dm): raccolta candidati, modalita PROVA->CSV, invio LIVE con cap/pause/kill-switch e CLI"
```

---

## Task 7: Verifica permesso dal vivo (`--test-uno`) — checkpoint umano

**Files:**
- Nessuna modifica di codice. Esecuzione controllata con l'utente.

> ⚠️ Questo task INVIA un DM reale. Da eseguire **solo col via dell'utente**, su un commento recente, preferibilmente di un account amministratore/tester per non disturbare un follower durante il test.

- [ ] **Step 1: PROVA su un post recente e revisione CSV**

Run: `python dm_bot.py --post <URL_POST_RECENTE>`
Expected: `dm_proposte.csv` popolato; l'utente controlla testi e destinatari.

- [ ] **Step 2: Invio singolo di verifica permesso**

Run: `python dm_bot.py --post <URL_POST_RECENTE> --live --test-uno`
Expected — due esiti possibili:
- **OK:** stampa `[DM] ...` e `--test-uno: inviato 1 DM`. Il permesso `pages_messaging` funziona col token attuale. Si può procedere ai giri piccoli.
- **Permesso mancante:** errore Graph tipo `(#200) ... pages_messaging` / "requires advanced access". → FERMARSI: serve la App Review di Meta per `pages_messaging` in Accesso Avanzato. Annotare l'errore esatto e passare a quella pratica prima di qualsiasi invio di massa.

- [ ] **Step 3: Registra l'esito**

Annota in `DOCUMENTAZIONE.md` (Task 8) se il permesso è attivo o se serve App Review, con la data e il messaggio d'errore eventuale.

---

## Task 8: Documentazione + versionamento stato

**Files:**
- Modify: `DOCUMENTAZIONE.md`
- Create/commit: `dm_inviati.json` (anche vuoto `{}` se non ancora generato)

- [ ] **Step 1: Aggiungi a `DOCUMENTAZIONE.md` la sezione "DM ai commentatori"**

Contenuto da inserire (adatta i titoli allo stile del file esistente):

```markdown
## DM ai commentatori (dm_bot.py)

Invia un messaggio privato (Private Reply) di ringraziamento + invito a seguire/like a chi
COMMENTA i post. Separato dal bot commenti. Non usa Claude (10 template a rotazione).

Vincoli Meta: raggiunge solo i commentatori (non chi reagisce), una volta per commento,
richiede il permesso `pages_messaging` (verso il pubblico generico serve Accesso Avanzato).
Non esiste API per sapere chi segue gia' la Pagina: il testo invita "se non lo fai gia'".

Regole: max 1 DM al giorno a persona (stato in dm_inviati.json), tetto globale --max-giorno
(default 150), pause 30-70s, nessun invio 00-06 ora italiana, stop a 3 errori di fila.

Uso:
  python dm_bot.py --ultimi-post 5                 # PROVA -> dm_proposte.csv (non invia)
  python dm_bot.py --post <URL> --live --test-uno  # invia 1 DM (verifica permesso)
  python dm_bot.py --ultimi-post 5 --live --max-giorno 20   # giro piccolo

Stato permesso pages_messaging: <DA COMPILARE dopo il Task 7: attivo / serve App Review>.
```

- [ ] **Step 2: Versiona lo stato DM**

```bash
python -c "import json,os; open('dm_inviati.json','x').write('{}') if not os.path.exists('dm_inviati.json') else None"
git add DOCUMENTAZIONE.md dm_inviati.json
git commit -m "docs(dm): documentazione dm_bot + versiona dm_inviati.json"
```

> Nota cloud (futuro): un eventuale workflow GitHub Actions dedicato dovrà aggiungere
> `dm_inviati.json` alla riga `git add` per persistere lo stato tra le esecuzioni. NON
> aggiungere ora il workflow: il rollout dei DM parte manuale (vedi spec, sezione Rollout).

---

## Note di esecuzione

- **Ordine:** Task 0 → 6 implementano e testano tutto offline. Task 7 è il primo invio reale
  (checkpoint umano). Task 8 chiude con docs e stato versionato.
- **Niente cron** in questo piano: il rollout cloud è una decisione successiva, da prendere solo
  dopo che `--test-uno` e i giri piccoli confermano che Meta non blocca.
- **Push:** seguire la policy del repo (commit + push) quando l'utente lo richiede; gli invii
  reali (Task 7) vanno fatti solo col suo via.
