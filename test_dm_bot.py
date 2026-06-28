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
