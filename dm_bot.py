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
