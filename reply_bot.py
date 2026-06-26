#!/usr/bin/env python3
"""
auto-commenti-fb (v2, ottimizzato) — risponde ai sostenitori sotto i post di una Pagina Facebook.

Ottimizzazioni rispetto alla v1 (per ridurre le chiamate/costo a Claude):
  1. SEEN-SET: ogni commento gia' analizzato (visti.json) viene saltato ai ri-lanci -> niente
     ri-classificazioni inutili (la v1 ri-pagava critici/neutri/volgari ad ogni giro).
  2. PRE-FILTRO a costo zero: commenti banali-positivi (emoji, "bravo", "top"...) ricevono una
     risposta da TEMPLATE a rotazione, senza toccare Claude.
  3. BATCHING: i commenti non banali vengono classificati a gruppi di ~18 in UNA chiamata
     (il system prompt si paga 1 volta ogni 18, non ad ogni commento).
  4. ARCHITETTURA A 2 FASI: prima classifica tutti (veloce/economico), poi pubblica con pause.

Modalita':
  python reply_bot.py --post <URL_o_ID>            # PROVA: genera proposte.csv, non pubblica
  python reply_bot.py --post <URL_o_ID> --live     # LIVE: pubblica davvero
  python reply_bot.py --ultimi-post 5 --live --max 20

Setup: vedi README.md
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import time

import requests

# Su Windows la console (cp1252) crasha stampando emoji: forziamo UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import anthropic
except ImportError:
    print("Manca il pacchetto 'anthropic'. Esegui:  pip install -r requirements.txt")
    sys.exit(1)

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# CONFIGURAZIONE
# ---------------------------------------------------------------------------

GRAPH_VERSION = "v21.0"
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"

# Modello Claude. Haiku = economico/veloce, ideale per risposte di una riga.
MODEL = "claude-haiku-4-5"
# MODEL = "claude-opus-4-8"   # piu' capace, costo maggiore

# Budget di token PER RISPOSTA (la qualita' la vedi alzando questo valore).
TOKEN_PER_RISPOSTA = 200
# Quanti commenti classificare in una sola chiamata (15-20 e' il compromesso ideale).
BATCH_SIZE = 18

# Pause (secondi) tra una risposta pubblicata e la successiva.
DELAY_MIN = 25
DELAY_MAX = 55

DONE_FILE = "done.json"      # id dei commenti gia' PUBBLICATI (per non ri-rispondere)
VISTI_FILE = "visti.json"    # id dei commenti gia' ANALIZZATI (per non ri-classificare)
LIKATI_FILE = "likati.json"  # id dei commenti a cui abbiamo gia' messo like
CSV_FILE = "proposte.csv"

# Like ai commenti sostenitori: azione leggera/basso rischio, pause brevi.
LIKE_DELAY_MIN = 3
LIKE_DELAY_MAX = 9

# ---------------------------------------------------------------------------
# PRE-FILTRO A COSTO ZERO (niente Claude per i commenti banali-positivi)
# ---------------------------------------------------------------------------

# Parole brevi chiaramente di sostegno (commenti di 1-2 parole -> template).
PAROLE_POSITIVE = {
    "bravo", "bravi", "brava", "brave", "grande", "grandi", "top", "ottimo", "ottima",
    "forza", "complimenti", "vero", "verissimo", "verissima", "esatto", "esatta",
    "giusto", "giusta", "condivido", "concordo", "perfetto", "perfetta", "applausi",
    "daje", "avanti", "bene", "benissimo", "sacrosanto", "sacrosanta", "evviva",
    "ottimi", "grazie", "splendido", "fenomeno", "mitico", "great", "wow",
}
# Emoji "positive" (se il commento e' solo emoji di queste -> template).
EMOJI_POSITIVE = set("💪❤️🔥🇮🇹👏👍🙏😍💙🤝✊❤👌🥰😘")
# Emoji ambigue/forti: NON le trattiamo da template, le mandiamo a Claude.
EMOJI_AMBIGUE = set("🤮🤬😡💩👎😤")

_re_parole = re.compile(r"[a-zàèéìòùA-ZÀÈÉÌÒÙ]+")


def e_banale_positivo(message):
    """True se il commento e' chiaramente di sostegno e cosi' breve da non meritare Claude."""
    msg = message.strip()
    if not msg:
        return False
    parole = [p.lower() for p in _re_parole.findall(msg)]
    if not parole:
        # solo emoji / punteggiatura
        chars = set(msg)
        if chars & EMOJI_AMBIGUE:
            return False
        return bool(chars & EMOJI_POSITIVE)
    # 1-2 parole, tutte chiaramente positive
    if len(parole) <= 2 and all(p in PAROLE_POSITIVE for p in parole):
        return True
    return False


# Template a rotazione per i banali-positivi (variati, per non cadere nell'identico).
TEMPLATES = [
    "Grazie mille! Se ti va condividi il post, aiuta a far girare 💪",
    "Grazie del sostegno! Una condivisione ci da' una grossa mano 🙏",
    "Grazie! Se condividi il post aiuti a far arrivare il messaggio a piu' gente 💪",
    "Troppo gentile, grazie! Condividi se sei d'accordo 👊",
    "Grazie di cuore! Fai girare il post se ti va, serve eccome 🙏",
    "Grazie del tuo sostegno! Condividi per dare piu' voce a queste idee 💪",
    "Apprezzo davvero, grazie! Se puoi condividi, ci aiuta tanto 🇮🇹",
    "Grazie! Conta molto il tuo sostegno. Condividi il post se ti va 💪",
    "Sei grande, grazie! Una condivisione fa la differenza 🙏",
    "Grazie mille per il sostegno! Fai girare il post se sei d'accordo 👊",
]


def scegli_template(contatore):
    return TEMPLATES[contatore % len(TEMPLATES)]


# ---------------------------------------------------------------------------
# CLAUDE — classificazione + risposta in BATCH (una chiamata per ~18 commenti)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """Sei l'assistente social di Gianmarco Porciani, creator politico (area sovranista/identitaria, Futuro Nazionale).
Gestisci le risposte ai commenti sotto i suoi post Facebook.

Ricevi PIU' commenti numerati. Per OGNI commento restituisci una voce con:
- n: il numero del commento
- categoria: una tra
   "sostenitore" (d'accordo, complimenti, indignazione allineata, sostiene la posizione del post)
   "critico" (attacca, dissente, polemizza, prende in giro)
   "neutro" (domande pratiche o commenti generici senza schieramento)
   "volgare" SOLO se contiene parolacce esplicite, insulti pesanti o bestemmie. NON classificare
   volgare un commento che usa parole forti ma è di SOSTEGNO (es. "traditori", "vergogna", "schifo",
   "fanno schifo" riferiti agli avversari/al sistema): quelli sono "sostenitore".
   "spam" (pubblicita', link, off-topic, bot)
- rispondere: true SOLO se categoria = "sostenitore", altrimenti false
- risposta: se rispondere=true, una risposta BREVE (1-2 frasi), calorosa, nel tono diretto di
  Gianmarco, che ringrazia e invita a condividere il post. Usa il nome se fornito. Varia sempre le
  parole, niente frasi identiche. Massimo una emoji (💪 🙏 👊 ❤️ 🇮🇹). Se rispondere=false, stringa vuota.

Restituisci SOLO il JSON nel formato richiesto, una voce per ogni commento ricevuto."""

BATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "risultati": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "categoria": {
                        "type": "string",
                        "enum": ["sostenitore", "critico", "neutro", "volgare", "spam"],
                    },
                    "rispondere": {"type": "boolean"},
                    "risposta": {"type": "string"},
                },
                "required": ["n", "categoria", "rispondere", "risposta"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["risultati"],
    "additionalProperties": False,
}


def classifica_batch(client, chunk):
    """chunk = lista di dict {cid, autore, message}. Ritorna {cid: {categoria, rispondere, risposta}}."""
    righe = []
    for i, it in enumerate(chunk, 1):
        nome = it["autore"] or "sconosciuto"
        testo = it["message"].replace("\n", " ")
        righe.append(f'[{i}] Nome: {nome} | Commento: "{testo}"')
    contenuto = "Ecco i commenti da classificare:\n\n" + "\n".join(righe)

    resp = client.messages.create(
        model=MODEL,
        max_tokens=len(chunk) * TOKEN_PER_RISPOSTA + 200,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": BATCH_SCHEMA}},
        messages=[{"role": "user", "content": contenuto}],
    )
    testo = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    data = json.loads(testo)
    out = {}
    for r in data.get("risultati", []):
        n = r.get("n")
        if isinstance(n, int) and 1 <= n <= len(chunk):
            out[chunk[n - 1]["cid"]] = r
    return out


def classifica_tutti(client, items):
    """Classifica TUTTI gli items a gruppi di BATCH_SIZE. Ritorna {cid: risultato}."""
    risultati = {}
    for i in range(0, len(items), BATCH_SIZE):
        chunk = items[i:i + BATCH_SIZE]
        try:
            risultati.update(classifica_batch(client, chunk))
            print(f"    classificati {min(i + BATCH_SIZE, len(items))}/{len(items)}")
        except Exception as e:
            print(f"    [errore classificazione batch {i // BATCH_SIZE + 1}] {e}")
    return risultati


# ---------------------------------------------------------------------------
# GRAPH API
# ---------------------------------------------------------------------------

def graph_get(path, token, params=None):
    p = {"access_token": token}
    if params:
        p.update(params)
    r = requests.get(f"{GRAPH}/{path}", params=p, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Graph GET {path} -> {r.status_code}: {r.text}")
    return r.json()


def graph_post(path, token, data):
    d = {"access_token": token}
    d.update(data)
    r = requests.post(f"{GRAPH}/{path}", data=d, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Graph POST {path} -> {r.status_code}: {r.text}")
    return r.json()


def get_page_info(token):
    me = graph_get("me", token, {"fields": "id,name"})
    return me["id"], me.get("name", "")


def estrai_post_id(arg, page_id):
    arg = arg.strip()
    if re.fullmatch(r"\d+_\d+", arg):
        return arg
    if re.fullmatch(r"\d+", arg):
        return f"{page_id}_{arg}"
    m = re.search(r"/posts/(\d+)", arg)
    if m:
        return f"{page_id}_{m.group(1)}"
    m = re.search(r"(?:story_fbid|fbid)=(\d+)", arg)
    if m:
        return f"{page_id}_{m.group(1)}"
    m = re.search(r"(pfbid\w+)", arg)
    if m:
        return m.group(1)
    return arg


def get_posts(token, page_id, limit):
    data = graph_get(f"{page_id}/posts", token,
                     {"fields": "id,message,created_time", "limit": limit})
    return data.get("data", [])


def _parse_comment(c, page_id):
    frm = c.get("from") or {}
    gia = False
    for rep in (c.get("comments", {}) or {}).get("data", []):
        rfrm = rep.get("from") or {}
        if rfrm.get("id") == page_id:
            gia = True
            break
    return {
        "id": c["id"],
        "message": c.get("message", "") or "",
        "autore_nome": frm.get("name", ""),
        "autore_id": frm.get("id", ""),
        "gia_risposto_pagina": gia,
    }


def get_comments(token, post_id, page_id):
    out = []
    data = graph_get(f"{post_id}/comments", token, {
        "fields": "id,message,from{id,name},comments.limit(100){from}",
        "limit": 100,
        "filter": "stream",
    })
    while True:
        for c in data.get("data", []):
            out.append(_parse_comment(c, page_id))
        nxt = (data.get("paging", {}) or {}).get("next")
        if not nxt:
            break
        r = requests.get(nxt, timeout=30)
        if r.status_code != 200:
            print(f"  [paginazione interrotta] {r.status_code}: {r.text[:200]}")
            break
        data = r.json()
    return out


def post_reply(token, comment_id, testo):
    return graph_post(f"{comment_id}/comments", token, {"message": testo})


def like_comment(token, comment_id):
    """Mette 'mi piace' (come Pagina) a un commento. L'API consente solo il like semplice."""
    return graph_post(f"{comment_id}/likes", token, {})


# ---------------------------------------------------------------------------
# STATO (done.json = pubblicati, visti.json = analizzati)
# ---------------------------------------------------------------------------

def _carica_set(path):
    try:
        with open(path, encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def _salva_set(path, s):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(sorted(s), f, ensure_ascii=False, indent=0)


# ---------------------------------------------------------------------------
# LAVORAZIONE DI UN POST (2 fasi: classifica, poi pubblica)
# ---------------------------------------------------------------------------

def lavora_post(client, token, page_id, post_id, live, done, visti, csv_writer,
                max_pub=None, no_like=False):
    print(f"\n=== Post {post_id} ===")
    commenti = get_comments(token, post_id, page_id)
    print(f"  {len(commenti)} commenti totali")

    autori_visti = set()    # per non rispondere 2 volte alla stessa persona su questo post
    da_rispondere = []      # {cid, autore, autore_id, risposta, categoria, fonte}
    da_classificare = []    # {cid, autore, autore_id, message}
    da_likare = []          # cid di TUTTI i sostenitori (anche quelli a cui non rispondiamo)
    tmpl_counter = 0
    n_saltati_gia = 0

    # ---- PRE-FILTRO (costo zero) ----
    for c in commenti:
        cid = c["id"]
        msg = c["message"].strip()
        autore_id = c["autore_id"]
        if not msg:
            continue
        if cid in done or cid in visti or c["gia_risposto_pagina"]:
            n_saltati_gia += 1
            continue
        if autore_id and autore_id in autori_visti:
            continue
        if e_banale_positivo(msg):
            da_likare.append(cid)
            risposta = scegli_template(tmpl_counter)
            tmpl_counter += 1
            da_rispondere.append({"cid": cid, "autore": c["autore_nome"], "autore_id": autore_id,
                                  "risposta": risposta, "categoria": "sostenitore", "fonte": "template"})
            if autore_id:
                autori_visti.add(autore_id)
            # NB: niente 'visti' qui: il template viene ri-riconosciuto gratis dal pre-filtro,
            # e va in done.json quando risposto. Cosi' non resta bloccato senza risposta.
        else:
            da_classificare.append({"cid": cid, "autore": c["autore_nome"],
                                    "autore_id": autore_id, "message": msg})

    print(f"  gia' gestiti (saltati): {n_saltati_gia} | banali->template: {tmpl_counter} | "
          f"da classificare con Claude: {len(da_classificare)}")

    # ---- FASE 1: classifica con Claude (in batch) ----
    risultati = classifica_tutti(client, da_classificare) if da_classificare else {}
    for it in da_classificare:
        cid = it["cid"]
        r = risultati.get(cid)
        cat = r.get("categoria", "?") if r else "errore"
        rispondo = bool(r and r.get("rispondere") and cat == "sostenitore")
        risposta = (r.get("risposta") or "").strip() if r else ""
        if cat == "sostenitore":
            da_likare.append(cid)   # like a TUTTI i sostenitori, anche se non rispondiamo
        csv_writer.writerow([post_id, it["autore"], it["message"][:120], cat,
                             "SI" if rispondo else "no", risposta])
        if rispondo and risposta:
            if it["autore_id"] not in autori_visti:
                da_rispondere.append({"cid": cid, "autore": it["autore"], "autore_id": it["autore_id"],
                                      "risposta": risposta, "categoria": cat, "fonte": "llm"})
                if it["autore_id"]:
                    autori_visti.add(it["autore_id"])
            # NB: i sostenitori da rispondere NON vengono segnati 'visti'. Vanno in done.json quando
            # risposti; se restano fuori per il tetto --max, al prossimo giro vengono ritentati.
        elif r is not None:
            # solo i NON-sostenitori (classificati con successo) vengono segnati 'visti' = saltati
            # per sempre senza ri-classificarli. Se r è None (errore), si ritenta al prossimo giro.
            visti.add(cid)
    # i template li mettiamo anche nel CSV
    for d in da_rispondere:
        if d["fonte"] == "template":
            csv_writer.writerow([post_id, d["autore"], "(banale)", "sostenitore", "SI", d["risposta"]])

    _salva_set(VISTI_FILE, visti)
    print(f"  sostenitori da likare: {len(da_likare)} | a cui risponderei: {len(da_rispondere)} "
          f"({tmpl_counter} template + {len(da_rispondere) - tmpl_counter} generate)")

    # ---- FASE 2: pubblica (solo in --live) ----
    if not live:
        for d in da_rispondere[:8]:
            print(f"  [PROVA] {d['autore']}: {d['risposta']}")
        if len(da_rispondere) > 8:
            print(f"  ...e altri {len(da_rispondere) - 8} (vedi {CSV_FILE})")
        return

    # ---- FASE 2a: like ai sostenitori (azione leggera) ----
    if not no_like and da_likare:
        likati = _carica_set(LIKATI_FILE)
        nuovi = [c for c in da_likare if c not in likati]
        print(f"  metto like a {len(nuovi)} commenti sostenitori...")
        n_like = 0
        for cid in nuovi:
            try:
                like_comment(token, cid)
                likati.add(cid)
                _salva_set(LIKATI_FILE, likati)
                n_like += 1
            except Exception as e:
                print(f"  [errore like {cid}] {e}")
            time.sleep(random.uniform(LIKE_DELAY_MIN, LIKE_DELAY_MAX))
        print(f"  like messi: {n_like}")

    # ---- FASE 2b: pubblica le risposte ----
    n_pub = 0
    errori = 0
    for d in da_rispondere:
        try:
            post_reply(token, d["cid"], d["risposta"])
            done.add(d["cid"])
            _salva_set(DONE_FILE, done)
            n_pub += 1
            errori = 0
            print(f"  [PUBBLICATO] {d['autore']}: {d['risposta']}")
        except Exception as e:
            errori += 1
            print(f"  [errore pubblicazione su {d['cid']}] {e}")
            if errori >= 3:
                print("  STOP: 3 errori di fila (token scaduto o blocco di Meta?). Mi fermo per sicurezza.")
                break
            continue
        if max_pub and n_pub >= max_pub:
            print(f"  Raggiunto il limite di {max_pub} risposte per questa sessione.")
            break
        pausa = random.uniform(DELAY_MIN, DELAY_MAX)
        print(f"    ...pausa {pausa:.0f}s")
        time.sleep(pausa)

    print(f"  Risposte pubblicate su questo post: {n_pub}")


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Risponde ai commenti dei sostenitori su Facebook")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--post", help="ID o URL del post da lavorare")
    g.add_argument("--ultimi-post", type=int, metavar="N",
                   help="lavora gli ultimi N post della pagina")
    ap.add_argument("--live", action="store_true",
                    help="pubblica davvero (senza questo flag e' solo PROVA: scrive proposte.csv)")
    ap.add_argument("--max", type=int, default=None, metavar="N",
                    help="in --live, pubblica al massimo N risposte per post (sicurezza anti-spam)")
    ap.add_argument("--no-like", action="store_true",
                    help="non mettere like ai commenti dei sostenitori (di default in --live li mette)")
    args = ap.parse_args()

    # Fascia notturna: in --live non si pubblica tra le 00:00 e le 06:00 (ora italiana),
    # cosi' l'attivita' si concentra negli orari in cui la gente e' online. La PROVA gira sempre.
    if args.live:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            ora_it = datetime.now(ZoneInfo("Europe/Rome")).hour
        except Exception:
            from datetime import datetime, timezone, timedelta
            ora_it = datetime.now(timezone(timedelta(hours=2))).hour  # fallback estate
        if ora_it < 6:
            print(f"Ora italiana ~{ora_it}:00 — fascia notturna (00-06): nessuna azione, a domani.")
            return

    token = os.environ.get("FB_PAGE_TOKEN")
    if not token:
        print("Manca FB_PAGE_TOKEN (.env). Vedi README.md")
        sys.exit(1)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Manca ANTHROPIC_API_KEY (.env). Vedi README.md")
        sys.exit(1)

    client = anthropic.Anthropic()
    page_id, page_name = get_page_info(token)
    print(f"Pagina: {page_name} (id {page_id})")
    print(f"Modalita': {'LIVE - pubblica' if args.live else 'PROVA - solo proposte.csv'}")
    print(f"Modello: {MODEL} | batch {BATCH_SIZE} | token/risposta {TOKEN_PER_RISPOSTA}")

    done = _carica_set(DONE_FILE)
    visti = _carica_set(VISTI_FILE)
    # AUTO-RECOVERY: un sostenitore a cui abbiamo messo like ma non ancora risposto NON deve
    # restare "visto" (altrimenti verrebbe saltato per sempre). Lo togliamo da visti -> ritentato.
    visti -= (_carica_set(LIKATI_FILE) - done)

    f_csv = open(CSV_FILE, "w", newline="", encoding="utf-8-sig")
    writer = csv.writer(f_csv)
    writer.writerow(["post_id", "autore", "commento", "categoria", "rispondo", "risposta_proposta"])

    try:
        if args.post:
            pid = estrai_post_id(args.post, page_id)
            lavora_post(client, token, page_id, pid, args.live, done, visti, writer,
                        args.max, args.no_like)
        else:
            posts = get_posts(token, page_id, args.ultimi_post)
            print(f"{len(posts)} post da lavorare")
            for p in posts:
                lavora_post(client, token, page_id, p["id"], args.live, done, visti, writer,
                            args.max, args.no_like)
    finally:
        f_csv.close()

    print(f"\nFatto. Proposte in {CSV_FILE}")
    if not args.live:
        print("Per pubblicare davvero, rilancia con --live")


if __name__ == "__main__":
    main()
