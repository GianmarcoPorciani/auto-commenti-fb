# Auto-risposte commenti Facebook

Risponde in automatico ai commenti dei **sostenitori** sotto i tuoi post Facebook, con
risposte brevi (ringraziamento + invito a condividere). Salta critici, volgari e spam.
Usa l'**API ufficiale** di Facebook (Graph API) + Claude per scrivere le risposte.

Due modalità:
- **PROVA** (default): legge i commenti, genera le risposte e le scrive in `proposte.csv`. **Non pubblica niente.**
- **LIVE** (`--live`): pubblica davvero, con pause anti-spam tra una risposta e l'altra.

---

## Setup una-tantum (~20 minuti)

### 0. Python e dipendenze
Serve Python 3.10+ installato. Poi, dentro questa cartella:
```
pip install -r requirements.txt
```

### 1. Crea un'app su Meta for Developers
1. Vai su https://developers.facebook.com/ → accedi col tuo account → **My Apps** → **Create App**.
2. Tipo app: scegli **Other** → **Business** (o "Nessuna" / "Altro"). Dai un nome (es. "Risposte Commenti").
3. Crea l'app. Non serve pubblicarla né farla revisionare per usarla **sulla tua pagina**.

### 2. Token Pagina (il pezzo importante)
Modo più veloce per partire (token temporaneo, ~1-2 ore — buono per le prove):
1. Vai su **Graph API Explorer**: https://developers.facebook.com/tools/explorer/
2. In alto a destra seleziona la tua app.
3. Clicca **Get Token** → **Get Page Access Token**.
4. Quando chiede i permessi, spunta:
   - `pages_show_list`
   - `pages_read_engagement`
   - `pages_manage_engagement`
5. Autorizza e **seleziona la tua Pagina** (Gianmarco Porciani).
6. Nel menu a tendina "User or Page" scegli **la tua Pagina**: il campo Token ora contiene il **token Pagina**. Copialo.

➡️ Incolla quel token in `.env` alla voce `FB_PAGE_TOKEN`.

> ⚠️ Quel token scade in poche ore. Per uno **a lunga durata** (~60 giorni) vedi sotto "Token a lunga durata".

### 3. Chiave API di Claude
1. Vai su https://console.anthropic.com/ → **API Keys** → crea una chiave.
2. Incollala in `.env` alla voce `ANTHROPIC_API_KEY`.

### 4. Crea il file .env
Copia `.env.example` in `.env` e riempi i due valori:
```
FB_PAGE_TOKEN=...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Uso

**Prima sempre una PROVA** (non pubblica niente, genera `proposte.csv` da controllare):
```
python reply_bot.py --post "https://www.facebook.com/GianmarcoPorciani1991/posts/XXXX"
```
Apri `proposte.csv` in Excel: vedi categoria assegnata e risposta proposta per ogni commento.

Quando sei convinto del tono, **pubblica davvero**:
```
python reply_bot.py --post "https://www.facebook.com/GianmarcoPorciani1991/posts/XXXX" --live
```

Lavorare gli **ultimi N post** della pagina in un colpo solo:
```
python reply_bot.py --ultimi-post 5 --live
```

Puoi passare a `--post` un URL del post **oppure** l'ID (es. `123..._456...`).

---

## Cosa fa, in regole

- Risponde **solo ai sostenitori** (Claude classifica ogni commento).
- **Non risponde due volte** alla stessa persona sullo stesso post.
- **Non risponde** a un commento a cui la Pagina ha già risposto.
- Tiene memoria in `done.json` dei commenti già gestiti: puoi rilanciarlo senza creare doppioni.
- Tra una risposta e l'altra fa una **pausa casuale** (25-55s) per non far scattare l'anti-spam.

## Regolare il comportamento

- **Tono delle risposte**: modifica `SYSTEM_PROMPT` in `reply_bot.py`.
- **Velocità / rischio spam**: alza `DELAY_MIN` / `DELAY_MAX` se Facebook inizia a limitare.
- **Costo**: in `reply_bot.py` cambia `MODEL` in `"claude-haiku-4-5"` (più economico e veloce,
  ideale per le risposte di una riga) — circa 5 volte meno costoso di Opus.

---

## Token a lunga durata (opzionale, per non rifarlo ogni volta)

Il token Pagina dell'Explorer scade in poche ore. Per uno che dura ~60 giorni:
1. Servono **App ID** e **App Secret** (in Meta for Developers → la tua app → Impostazioni → Basic).
2. Con un token utente a breve durata, scambia per uno utente a lunga durata:
   ```
   https://graph.facebook.com/v21.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=TOKEN_BREVE
   ```
3. Con quel token utente a lunga durata, chiama `https://graph.facebook.com/v21.0/me/accounts`:
   il token della tua Pagina lì dentro è **a lunga durata** (non scade finché non cambi password).

(Se vuoi, posso scriverti uno script `get_token.py` che fa questi due passaggi in automatico.)

---

## Note e limiti

- Anche con l'API ufficiale, l'automazione di massa dei commenti è una zona "grigia" per le policy
  Meta: con pause ragionevoli e testi variati il rischio è basso, ma esiste. Per questo c'è la pausa
  anti-spam e la modalità PROVA.
- Il campo con il **nome** di chi commenta potrebbe non arrivare per tutti i profili (dipende dai
  permessi/privacy): in quel caso la risposta viene comunque generata, solo senza nome.
- `done.json` e `proposte.csv` vengono creati nella cartella al primo avvio.
