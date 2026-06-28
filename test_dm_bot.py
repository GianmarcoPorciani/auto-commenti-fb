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
