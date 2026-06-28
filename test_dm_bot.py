import dm_bot


def test_nome_breve_estrae_il_primo_nome():
    assert dm_bot.nome_breve("Mario Rossi") == "Mario"
    assert dm_bot.nome_breve("Anna") == "Anna"
    assert dm_bot.nome_breve("  Luca   Bianchi ") == "Luca"
    assert dm_bot.nome_breve("") == ""
    assert dm_bot.nome_breve(None) == ""
    assert dm_bot.nome_breve("   ") == ""


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
