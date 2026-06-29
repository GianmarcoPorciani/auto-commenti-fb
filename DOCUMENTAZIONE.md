# Bot Auto-Risposte Commenti Facebook — Documentazione

**Progetto:** automazione community management della Pagina Facebook **Gianmarco Porciani** (Futuro Nazionale)
**Stato:** operativo, in cloud, attivo 24/7
**Repository:** https://github.com/GianmarcoPorciani/auto-commenti-fb (privato)
**Ultimo aggiornamento doc:** 29 giugno 2026

---

## 1. Cosa fa, in breve

Un sistema che gestisce **da solo** i commenti sotto i post della Pagina:

- **Legge** i commenti via API ufficiale di Facebook
- **Classifica** ogni commento con l'AI (Claude): sostenitore / critico / neutro / volgare / spam
- **Risponde** solo ai **sostenitori**, con messaggi brevi nel tono di Gianmarco, che ringraziano e
  invitano a condividere il post + mettere like alla Pagina (se non già fatto). Usa il **nome** di chi
  commenta quando Facebook lo fornisce (≈1 commento su 4: per gli altri il nome è oscurato per privacy)
- **Mette like** a tutti i commenti dei sostenitori
- **Non risponde** a critici, volgari, spam (ma non li censura: restano lì e fanno volume)
- Gira **in cloud ogni ora** di giorno (≈06–24 ora italiana), con **giri "lampo" extra** sui post
  appena pubblicati (spinta "ora d'oro"); di **notte (00–06) sta fermo**. Tutto a PC spento.

In più, due strumenti "a comando":
- **Creazione post** (testo scritto da te o generato dall'AI, con foto e primo commento "@follower")
- **Report statistiche** della Pagina (reazioni, arrabbiati, click, commenti, condivisioni per post)

---

## 2. Come funziona il bot dei commenti (architettura)

Il programma principale è `reply_bot.py`. Per ogni post lavora in **due fasi**:

**Pre-filtro (a costo zero, senza AI)**
- Salta i commenti già gestiti (memoria persistente, vedi sotto)
- Salta i commenti **scritti dalla Pagina stessa** (altrimenti il bot rischierebbe di mettere like e
  rispondere ai propri commenti)
- Salta i commenti a cui la Pagina ha già risposto
- Salta i doppioni dello stesso autore sullo stesso post
- I commenti **banali e positivi** (emoji, "bravo", "top"...) ricevono una **risposta da template a
  rotazione** (16 varianti: 8 con il nome di chi commenta + 8 neutre), senza chiamare l'AI

**Fase 1 — Classificazione (AI)**
- Tutti i commenti "veri" vengono mandati a Claude **a gruppi di 18 per chiamata** (batch)
- Claude restituisce per ognuno: categoria + se rispondere + il testo della risposta
- Risultato: si capisce chi è sostenitore e si ha già la risposta pronta

**Fase 2 — Pubblicazione**
- Mette **like** a tutti i sostenitori (azione leggera, pause brevi 3-9 secondi)
- **Pubblica le risposte** ai sostenitori, con **pause di 25-55 secondi** tra una e l'altra (anti-spam)
- Si **ferma da solo** se riceve 3 errori di fila (es. blocco di Meta) — sicurezza

> **Robustezza di rete:** ogni chiamata a Facebook passa da un **retry automatico con attesa
> esponenziale** (3 → 6 → 12s, fino a 4 tentativi) sui soli errori **temporanei** (HTTP 5xx,
> `is_transient`, rate-limit). Un singolo 500 momentaneo di Meta non fa più fallire l'intero giro.
> Gli errori **permanenti** (token scaduto, permessi) vengono invece segnalati subito.

### Memoria persistente (niente doppioni, niente sprechi)
Quattro file ricordano lo stato tra un giro e l'altro:
- `done.json` — commenti a cui è già stata pubblicata una risposta
- `visti.json` — commenti già analizzati (così ai giri successivi **non si ri-paga** la classificazione)
- `likati.json` — commenti a cui è già stato messo like
- `coda.json` — **coda delle risposte pronte**: ogni sostenitore viene classificato **una volta sola**;
  la risposta resta in coda e i giri successivi la pubblicano senza ri-chiamare Claude. La coda si
  **auto-pulisce** alla pubblicazione (entra in classificazione, esce in `done.json`). Garantisce che
  **nessun sostenitore venga mai dimenticato**, anche se il tetto di risposte per giro lascia un arretrato.

Grazie a questi, ogni giro lavora **solo i commenti nuovi**: rapido ed economico.

> **Stato a prova di conflitto:** quando due giri si accavallano, lo stato non si può più azzerare.
> Prima di salvare, `merge_stato.py` **unisce** la versione locale e quella remota di ogni file (per gli
> insiemi la fusione corretta è sempre l'unione). E se un file arrivasse comunque danneggiato, il
> caricatore recupera gli ID dal testo grezzo invece di ripartire da vuoto.

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
| `reply_bot.py` | Il bot principale: legge, classifica, risponde, mette like (con retry anti-errori temporanei) |
| `merge_stato.py` | Unisce lo stato locale+remoto prima del salvataggio (evita azzeramenti da conflitti git) |
| `crea_post.py` | Pubblica un post (testo tuo o generato dall'AI) + foto + primo commento @follower |
| `dm_bot.py` | Messaggi privati ai commentatori (vedi sezione dedicata — richiede `pages_messaging`, non ancora attivo) |
| `insights.py` | Report statistiche della Pagina |
| `get_token.py` | Utility per rigenerare un token a lunga durata (raramente serve, vedi sotto) |
| `requirements.txt` | Le librerie necessarie |
| `.env` | I segreti (token + chiave AI) — **solo in locale, mai su GitHub** |
| `.github/workflows/bot.yml` | Giro orario (di giorno) |
| `.github/workflows/bot-burst.yml` | Giri "lampo" sui post freschi (spinta "ora d'oro") |
| `done/visti/likati/coda.json` | La memoria persistente |
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
- **Pianificazione:** due workflow complementari, entrambi attivi solo di giorno (cron in UTC `4-22`,
  ≈06–24 ora italiana; il bot stesso salta comunque le 00–06 per gestire bene ora legale/solare):
  - `bot.yml` — **giro orario** al minuto :00 (`cron "0 4-22 * * *"`), ultimi 5 post, max 40 risposte/post
  - `bot-burst.yml` — **giri "lampo"** ai minuti :20 e :40 (`cron "20,40 4-22 * * *"`), ma solo se c'è un
    post pubblicato da meno di 3 ore (altrimenti esce subito, a costo zero). Stesso "concurrency group":
    i due non si sovrappongono mai
- **Cosa fa a ogni giro:** mette like ai sostenitori e risponde ai commenti nuovi, saltando tutto ciò
  che è già stato fatto e svuotando la coda delle risposte pendenti
- **Segreti:** token Facebook e chiave Claude sono nei *GitHub Secrets* (cifrati, non nel codice)
- **Stato:** dopo ogni giro i file di memoria (`done/visti/likati/coda.json`) vengono **uniti** con la
  versione nel repo e ri-salvati (vedi "Stato a prova di conflitto"), così il giro successivo riprende
  esattamente da dove era — senza rischio di azzeramenti se due giri si accavallano

### Come controllarlo / avviarlo a mano
Vai sul repo → scheda **Actions** → workflow "auto-commenti-fb" → **Run workflow** (avvio manuale).
Lì vedi anche lo storico di tutti i giri (riusciti/falliti).

> ⚠️ **Importante:** una volta attivo il cloud, **non lanciare più il bot dal PC in parallelo**: il cloud
> è la "verità", girare anche in locale creerebbe due memorie separate e possibili doppioni.

---

## 6. Come si usa

### Commenti → automatico
Non devi fare niente. Ogni ora (di giorno) il bot risponde e mette like ai commenti nuovi, con giri
"lampo" extra quando pubblichi un post fresco.

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
- **Invitare le persone a mettere "mi piace" alla Pagina** → **non esiste** un'API: l'invito è solo
  quello *testuale* dentro la risposta ("se non segui già la pagina, mettile un like")
- **Nome di chi commenta** → Facebook lo fornisce solo per ≈1 commento su 4 (privacy); per gli altri il
  campo arriva vuoto e non c'è modo di recuperarlo. Le risposte usano il nome **dove c'è**, mai inventato
- **@tag cliccabile del commentatore** → valutato e scartato: serve l'ID (disponibile solo dove c'è il
  nome) ed è fragile; la risposta annidata notifica comunque già la persona
- **Commentare su altre Pagine** → richiede permessi speciali con revisione di Meta, ad alto rischio: sconsigliato
- **Copertura/impression dei post** → non più esposte dall'API in questa versione
- **Risposte automatiche su Messenger** → tecnicamente possibili ma è un progetto a parte (server sempre
  acceso + revisione Meta + regole sulle 24h): valutato e rimandato

---

## 8. Note di buon senso (policy Meta)

L'automazione dei commenti è una zona "grigia" per le regole di Meta. Il sistema è costruito per starci dentro:
- **pause tra le risposte** (25-55s) e like distribuiti, per non sembrare un bot
- **risposte sempre variate** (l'AI non ripete frasi identiche; i template ruotano e usano il nome)
- **stop automatico** se Meta inizia a bloccare; **retry con backoff** solo sugli errori temporanei
- **fascia notturna** (00-06) di silenzio, volume ragionevole per giro

Restano comunque consigli: non alzare troppo la frequenza, e tenere d'occhio che le risposte restino di qualità.

---

## 9. Manutenzione e problemi comuni

| Situazione | Cosa fare |
|------------|-----------|
| Ti arriva un'email "Run failed" da GitHub | Ora gli errori temporanei di Meta vengono ritentati in automatico: se l'email arriva lo stesso, è probabile un problema **reale** (es. token da rigenerare). Apri il log dalla scheda Actions per la causa. |
| Vuoi cambiare la frequenza | Modifica i `cron` in `.github/workflows/bot.yml` e `bot-burst.yml` |
| Vuoi cambiare il tono / i template delle risposte | Modifica `SYSTEM_PROMPT` e le liste `TEMPLATES_NOME`/`TEMPLATES_NEUTRO` in `reply_bot.py` |
| Vuoi cambiare gli orari di silenzio notturno | Modifica la fascia 00-06 in `main()` di `reply_bot.py` e i `cron` dei workflow |
| Meta blocca i commenti | Il bot si ferma da solo; aspetta qualche ora e riprende al giro successivo |
| Un contatore di stato sembra "calato" (es. `likati.json`) | Innocuo: lo stato si ricostruisce da solo e l'unione impedisce perdite reali. `done.json` (anti-doppioni) è quello critico ed è protetto. |
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
8. **Messo in cloud su GitHub Actions**: lavora da solo, indipendente dal PC
9. **Pianificazione affinata:** giro orario + giri "lampo" sui post freschi + **fascia notturna** 00-06
10. **Coda delle risposte pendenti** (`coda.json`): copertura garantita di tutti i sostenitori, anche
    oltre il tetto per giro, e niente ri-classificazioni costose
11. Corretto il bug che faceva mettere like / processare i **commenti della Pagina stessa**
12. **Risposte più personali:** uso del nome di battesimo quando disponibile + template variati
13. **Robustezza:** retry con backoff sugli errori temporanei di Meta; **stato a prova di conflitto**
    (unione locale+remoto) per non azzerare mai la memoria quando due giri si accavallano

**Risultato:** un sistema di community management autonomo, economico, resiliente e sempre attivo per la Pagina.

---

## DM ai commentatori (dm_bot.py)

Invia un messaggio privato (Private Reply) di ringraziamento + invito a seguire/like a chi
COMMENTA i post. Separato dal bot commenti. Non usa Claude (10 template a rotazione).

Vincoli Meta: raggiunge solo i commentatori (non chi reagisce), una volta per commento,
richiede il permesso `pages_messaging` (verso il pubblico generico serve Accesso Avanzato).
Non esiste API per sapere chi segue gia' la Pagina: il testo invita "se non lo fai gia'".
Facebook NON espone l'identita' di chi commenta (autore_id/nome vuoti): dedup e cap sono
quindi per COMMENTO (1 DM per commento) e i messaggi usano la versione senza nome.

Regole: 1 DM per commento (stato in dm_inviati.json, chiave = comment_id), tetto globale
--max-giorno (default 150), pause 30-70s, nessun invio 00-06 ora italiana, stop a 3 errori.

Uso:
  python dm_bot.py --ultimi-post 5                    # PROVA -> dm_proposte.csv (non invia)
  python dm_bot.py --commento <COMMENT_ID> --live     # invia a un commento preciso (test mirato)
  python dm_bot.py --post <URL> --live --test-uno     # invia 1 DM (verifica permesso)
  python dm_bot.py --ultimi-post 5 --live --max-giorno 20   # giro piccolo

Stato permesso pages_messaging (verificato 2026-06-28 via debug_token): **NON ATTIVO**.
Il token Pagina (Utente di Sistema, app 1529398511958436) ha business_management,
pages_manage_engagement/metadata/posts, pages_read_engagement/user_content, pages_show_list,
read_insights — ma NON pages_messaging. Il primo invio di prova e' fallito con
400 / code 100 / subcode 33 (object/permissions). Per attivare i DM serve:
  1. Aggiungere il prodotto/permesso pages_messaging all'app su Meta for Developers.
  2. Rigenerare il token dell'Utente di Sistema includendo lo scope pages_messaging.
  3. Per inviare al PUBBLICO (non solo admin/tester) serve l'Accesso Avanzato di
     pages_messaging tramite App Review di Meta.
Finche' il punto 3 non e' approvato, le private reply funzionano solo verso persone con
un ruolo sulla Pagina o tester dell'app.
