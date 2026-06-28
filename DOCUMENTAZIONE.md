# Bot Auto-Risposte Commenti Facebook — Documentazione

**Progetto:** automazione community management della Pagina Facebook **Gianmarco Porciani** (Futuro Nazionale)
**Stato:** operativo, in cloud, attivo 24/7
**Repository:** https://github.com/GianmarcoPorciani/auto-commenti-fb (privato)
**Ultimo aggiornamento doc:** 24 giugno 2026

---

## 1. Cosa fa, in breve

Un sistema che gestisce **da solo** i commenti sotto i post della Pagina:

- **Legge** i commenti via API ufficiale di Facebook
- **Classifica** ogni commento con l'AI (Claude): sostenitore / critico / neutro / volgare / spam
- **Risponde** solo ai **sostenitori**, con messaggi brevi nel tono di Gianmarco, che ringraziano e invitano a condividere il post
- **Mette like** a tutti i commenti dei sostenitori
- **Non risponde** a critici, volgari, spam (ma non li censura: restano lì e fanno volume)
- Gira **in cloud ogni 2 ore**, anche a PC spento

In più, due strumenti "a comando":
- **Creazione post** (testo scritto da te o generato dall'AI, con foto e primo commento "@follower")
- **Report statistiche** della Pagina (reazioni, arrabbiati, click, commenti, condivisioni per post)

---

## 2. Come funziona il bot dei commenti (architettura)

Il programma principale è `reply_bot.py`. Per ogni post lavora in **due fasi**:

**Pre-filtro (a costo zero, senza AI)**
- Salta i commenti già gestiti (memoria persistente, vedi sotto)
- Salta i commenti a cui la Pagina ha già risposto
- Salta i doppioni dello stesso autore sullo stesso post
- I commenti **banali e positivi** (emoji, "bravo", "top"...) ricevono una **risposta da template a rotazione** (10 varianti), senza chiamare l'AI

**Fase 1 — Classificazione (AI)**
- Tutti i commenti "veri" vengono mandati a Claude **a gruppi di 18 per chiamata** (batch)
- Claude restituisce per ognuno: categoria + se rispondere + il testo della risposta
- Risultato: si capisce chi è sostenitore e si ha già la risposta pronta

**Fase 2 — Pubblicazione**
- Mette **like** a tutti i sostenitori (azione leggera, pause brevi 3-9 secondi)
- **Pubblica le risposte** ai sostenitori, con **pause di 25-55 secondi** tra una e l'altra (anti-spam)
- Si **ferma da solo** se riceve 3 errori di fila (es. blocco di Meta) — sicurezza

### Memoria persistente (niente doppioni, niente sprechi)
Tre file ricordano lo stato tra un giro e l'altro:
- `done.json` — commenti a cui è già stata pubblicata una risposta
- `visti.json` — commenti già analizzati (così ai giri successivi **non si ri-paga** la classificazione)
- `likati.json` — commenti a cui è già stato messo like

Grazie a questi, ogni giro lavora **solo i commenti nuovi**: rapido ed economico.

### Ottimizzazioni costi (perché spende pochissimo)
- **Pre-filtro a codice**: i commenti banali non toccano l'AI → meno volume
- **Batch da 18**: le istruzioni (system prompt) si pagano 1 volta ogni 18 commenti, non ogni volta
- **Seen-set**: i commenti già visti non si ri-classificano
- **Modello economico** (Claude Haiku) per risposte brevi

Stima reale: **pochi centesimi al giorno** anche su post molto attivi.

> Nota tecnica: il *prompt caching* di Anthropic **non** è usato perché su Haiku serve un prompt da almeno
> 4096 token e il nostro è ~600 (sotto soglia, non si attiverebbe). Il risparmio vero viene dal batching.

---

## 3. I file del progetto

| File | A cosa serve |
|------|--------------|
| `reply_bot.py` | Il bot principale: legge, classifica, risponde, mette like |
| `crea_post.py` | Pubblica un post (testo tuo o generato dall'AI) + foto + primo commento @follower |
| `insights.py` | Report statistiche della Pagina |
| `get_token.py` | Utility per rigenerare un token a lunga durata (raramente serve, vedi sotto) |
| `requirements.txt` | Le librerie necessarie |
| `.env` | I segreti (token + chiave AI) — **solo in locale, mai su GitHub** |
| `.github/workflows/bot.yml` | La pianificazione cloud "ogni 2 ore" |
| `done/visti/likati.json` | La memoria persistente |
| `README.md` | Istruzioni d'uso rapide |

---

## 4. Configurazione Facebook (fatta una volta)

### App Meta
- **Nome app:** "Risposte Commenti" — **App ID:** `1529398511958436`
- Creata su developers.facebook.com con caso d'uso "Gestisci tutto sulla tua Pagina" (API Pages)

### Pagina
- **Gianmarco Porciani** — **Page ID:** `504760203329428` (URL pubblico: facebook.com/GianmarcoPorciani1991)
- È una Pagina "New Pages Experience": per gestirla via API serve anche il permesso `business_management`

### Token che NON scade (il punto chiave)
Il token serve al bot per agire come la Pagina. Per farlo funzionare **in cloud 24/7** serve un token
**che non scada mai**. Ottenuto tramite un **Utente di Sistema** del Business Manager:

1. business.facebook.com → Impostazioni dell'azienda (ZanzOut)
2. Collegata l'app "Risposte Commenti" all'azienda
3. Creato un Utente di Sistema "bot-commenti" (ruolo Amministratore)
4. Assegnati all'utente di sistema: la Pagina (controllo completo) e l'app
5. Generato un token con scadenza **"Mai"** e tutti i permessi

Il token risultante **non scade** e ha tutti i permessi: rispondere, like, creare post, leggere statistiche.

> **Sicurezza:** token, chiave API e App Secret **non** sono in questo documento. Vivono solo nel file
> `.env` (in locale) e nei *GitHub Secrets* cifrati del repository.

---

## 5. L'automazione cloud (GitHub Actions)

Il bot gira sui server di GitHub, **gratis**, senza bisogno che il PC sia acceso.

- **Repository privato:** `GianmarcoPorciani/auto-commenti-fb`
- **Pianificazione:** ogni 2 ore (file `.github/workflows/bot.yml`, cron `0 */2 * * *`)
- **Cosa fa a ogni giro:** sugli **ultimi 5 post**, mette like ai sostenitori e risponde ai commenti
  nuovi (massimo 25 risposte per post, per sicurezza), saltando tutto ciò che è già stato fatto
- **Segreti:** token Facebook e chiave Claude sono nei *GitHub Secrets* (cifrati, non nel codice)
- **Stato:** dopo ogni giro, i file di memoria (`done/visti/likati.json`) vengono ri-salvati nel repo,
  così il giro successivo riprende esattamente da dove era

### Come controllarlo / avviarlo a mano
Vai sul repo → scheda **Actions** → workflow "auto-commenti-fb" → **Run workflow** (avvio manuale).
Lì vedi anche lo storico di tutti i giri (riusciti/falliti).

> ⚠️ **Importante:** una volta attivo il cloud, **non lanciare più il bot dal PC in parallelo**: il cloud
> è la "verità", girare anche in locale creerebbe due memorie separate e possibili doppioni.

---

## 6. Come si usa

### Commenti → automatico
Non devi fare niente. Ogni 2 ore il bot risponde e mette like ai commenti nuovi.

### Creare un post → a comando (`crea_post.py`)
- Scrivi tu il testo, **oppure** lo genera l'AI da un tema, **tu approvi**, poi si pubblica
- Puoi allegare una **foto** e programmare data/ora
- Dopo la pubblicazione, mette in automatico il primo commento **"@follower"**
- ⚠️ Da verificare se il tag "@follower" via API fa scattare davvero la notifica ai follower (è un tag
  speciale dell'app Facebook): se non funzionasse, quel singolo commento si fissa a mano in 5 secondi

### Statistiche → a comando (`insights.py`)
Mostra, per gli ultimi post: **reazioni totali, "arrabbiati" 😡, commenti, condivisioni, click**.
Il numero di "arrabbiati" è un ottimo termometro di quanto un post fa discutere/infastidisce gli avversari.

> Nota: le metriche di **copertura/impression** non sono più esposte dall'API di Facebook in questa
> versione, quindi non compaiono. Reazioni, click ed engagement sì.

---

## 7. Cosa NON è possibile (limiti di Facebook)

- **Reazioni diverse dal like** (Love, Arrabbiato...) via API → **non si possono** pubblicare: l'API
  consente solo il "like" semplice
- **Invitare le persone a mettere "mi piace" alla Pagina** → **non esiste** un'API: solo a mano dall'app
- **Commentare su altre Pagine** → richiede permessi speciali con revisione di Meta, ad alto rischio: sconsigliato
- **Copertura/impression dei post** → non più esposte dall'API in questa versione
- **Risposte automatiche su Messenger** → tecnicamente possibili ma è un progetto a parte (server sempre
  acceso + revisione Meta + regole sulle 24h): valutato e rimandato

---

## 8. Note di buon senso (policy Meta)

L'automazione dei commenti è una zona "grigia" per le regole di Meta. Il sistema è costruito per starci dentro:
- **pause tra le risposte** (25-55s) e like distribuiti, per non sembrare un bot
- **risposte sempre variate** (l'AI non ripete frasi identiche; i template ruotano)
- **stop automatico** se Meta inizia a bloccare
- volume ragionevole per giro

Restano comunque consigli: non alzare troppo la frequenza, e tenere d'occhio che le risposte restino di qualità.

---

## 9. Manutenzione e problemi comuni

| Situazione | Cosa fare |
|------------|-----------|
| Il giro cloud "fallisce" (scheda Actions) | Apri il log: di solito è un limite temporaneo di Meta. Riparte da solo al giro dopo. |
| Vuoi cambiare la frequenza | Modifica il cron in `.github/workflows/bot.yml` (es. `0 */3 * * *` = ogni 3 ore) |
| Vuoi cambiare il tono delle risposte | Modifica `SYSTEM_PROMPT` in `reply_bot.py` |
| Meta blocca i commenti | Il bot si ferma da solo; aspetta qualche ora e riprende al giro successivo |
| Il token smette di funzionare (raro, es. cambio password / permessi revocati) | Rigenera il token dall'Utente di Sistema (Business Manager) e aggiornalo nei GitHub Secrets |

---

## 10. Sintesi del percorso svolto

1. Risposte iniziali pubblicate a mano (test del tono) sul post "Mediaset / Mario Giordano"
2. Costruito il bot via **API ufficiale** di Facebook + **Claude** per classificare e scrivere
3. Risolto il nodo "Pagina New Pages Experience" (serviva il permesso `business_management`)
4. Pubblicate ~96 risposte ai sostenitori (test reali, 0 errori, Meta non ha bloccato)
5. **Ottimizzato** il bot: pre-filtro, batch, memoria persistente → costi ridotti al minimo
6. Aggiunti **like ai sostenitori**, **creazione post**, **report statistiche**
7. Ottenuto un **token che non scade** tramite Utente di Sistema (sblocca tutti i permessi)
8. **Messo in cloud su GitHub Actions**: lavora da solo ogni 2 ore, indipendente dal PC

**Risultato:** un sistema di community management autonomo, economico e sempre attivo per la Pagina.

---

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
