# Benchmark modello locale sulla classificazione commenti — 2026-07-28

**Domanda:** il modello locale (Ollama, Dolphin Mistral 24B Venice IQ4_XS) può sostituire
`claude-haiku-4-5` in `reply_bot.py`, azzerando il costo API?

**Risposta: no.** Numeri sotto. Non ritentare senza prima cambiare l'approccio al prompt.

## Metodo

`benchmark_locale.py` — campione stratificato da `proposte.csv` (l'unico file con i
**testi** dei commenti; `classificati.json` ha solo `id → categoria`). Il system prompt
è **importato** da `reply_bot.py`, non ricopiato. Seed fisso: esecuzioni confrontabili.
Riferimento = le categorie assegnate da Claude in produzione.

Campione: 65 commenti (20 sostenitore, 20 critico, 20 neutro, 4 volgare, 1 spam — le
ultime due categorie sono sotto-rappresentate in `proposte.csv`, che ha solo 141 righe).

## Risultati

| Batch | Accordo con Claude | Errori gravi¹ |
|---|---|---|
| 20 (come produzione) | 36,9% | 11/65 — 16,9% |
| 5 | 40,0% | 16/65 — 24,6% |
| 1 | 38,5% | **25/65 — 38,5%** |

¹ commento `critico`/`volgare`/`spam` classificato `sostenitore` → il bot pubblica un
ringraziamento sotto un attacco.

**L'ipotesi "i batch grandi confondono il modello" è falsificata.** Ridurre il batch non
migliora l'accordo e *peggiora* gli errori gravi.

## Perché fallisce — a batch 1 il classificatore degenera

| Categoria | Accordo a batch 1 |
|---|---|
| sostenitore | **19/20 (95%)** |
| critico | **0/20 (0%)** — tutti letti come sostenitore |
| neutro | 6/20 (30%) |
| volgare | 0/4 |
| spam | 0/1 |

60 commenti su 65 classificati `sostenitore`: il modello collassa sulla classe
maggioritaria. L'accordo del 38,5% è quasi solo la frequenza di base dei sostenitori,
non capacità di discriminare.

**Causa probabile: il prompt è tarato su Claude.** Contiene
`"Tieni l'asticella BASSA: in dubbio [...] scegli SEMPRE sostenitore"`. Claude ha la
finezza per riconoscere quando *non* c'è dubbio; il 24B prende l'istruzione alla lettera
e sceglie sostenitore sempre. Isolando il commento (batch 1) sparisce anche il contrasto
con gli altri commenti del batch, e il collasso è totale.

## Cosa NON è stato provato

- Un prompt **riscritto per il modello locale**: senza il bias verso `sostenitore`, con
  esempi few-shot per `critico` e `volgare`. È la sola strada tecnica rimasta credibile.
- Modelli diversi (Qwen, Gemma). Il compito è classificazione, non scrittura: un modello
  più piccolo ma addestrato meglio sulla comprensione potrebbe fare di più.

## Il contesto che pesa più dei numeri

I commenti su cui il modello sbaglia venivano da un post sulla morte di una persona
(*"Uno di meno"*, *"Ben gli sta un ladro in meno"*, *"si è fatto giustizia da solo 🤣"*).
Claude li marca `volgare`/`critico`; il modello locale `sostenitore`.

Da notare: **la lettera del prompt darebbe ragione al modello locale** — dice "volgare
solo se l'offesa è rivolta a NOI". La scelta di Claude è più prudente di quanto il prompt
richieda. Indipendentemente da quale modello si usi, vale la pena rivedere la regola:
una risposta automatica di ringraziamento sotto un commento che esulta per un morto è un
danno reputazionale che nessun risparmio compensa.

## Costo attuale, per riferimento

`claude-haiku-4-5` a $1/$5 per Mtok · system prompt 859 token · batch da 20 ≈ 0,8
centesimi · ~15.700 commenti classificati finora ≈ **6 dollari in totale**, circa **4-5
$/mese**. Prompt caching non applicabile: 859 token contro i 4096 minimi di Haiku 4.5.
