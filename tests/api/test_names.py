"""Short fund names for the screens (docs/web-ui.md "Redesign v2")."""

import pytest

from rmprep.api.names import short_name


@pytest.mark.parametrize("label,issuer,short", [
    ("NUROL PORTFÖY PARA PİYASASI (TL) FONU", "Nurol Portföy", "Para Piyasası (TL)"),
    ("İSTANBUL PORTFÖY KISA VADELİ BORÇLANMA ARAÇLARI (TL) FONU", "İstanbul Portföy",
     "KV Borçlanma (TL)"),
    ("AK PORTFÖY PARA PİYASASI KATILIM FONU", "Ak Portföy", "Para Piyasası Katılım"),
    ("GARANTİ  PORTFÖY HOLDİNGLER VE İŞTİRAKLERİ HİSSE SENEDİ (TL) FONU (HİSSE SENEDİ YOĞUN FON)",
     "Garanti Portföy", "Holdingler ve İştirakleri Hisse Senedi (TL) (Hisse Senedi Yoğun Fon)"),
])
def test_short_names(label, issuer, short):
    assert short_name(label) == (issuer, short)


def test_short_name_turkish_case():
    assert short_name("ZİRAAT PORTFÖY BİRİNCİ IŞIK FONU") == ("Ziraat Portföy", "Birinci Işık")


def test_short_name_without_portfoy():
    assert short_name("ING Turuncu Hesap (standart)") == ("", "ING Turuncu Hesap (standart)")
    assert short_name("ING e-Vadeli Mevduat") == ("", "ING e-Vadeli Mevduat")


def test_short_name_only_portfoy_word():
    assert short_name("X PORTFÖY FONU") == ("X Portföy", "X PORTFÖY FONU")


def test_option_view_has_short_names(backend, persona):
    from fastapi.testclient import TestClient

    from rmprep.api.app import create_app
    from rmprep.api.views import ViewBuilder
    from rmprep.decision import load_config
    c = TestClient(create_app(backend, views=ViewBuilder(backend, load_config())))
    v = c.post("/api/runs", json={"persona": persona}).json()
    for o in v["options"].values():
        assert {"issuer", "short_label"} <= set(o) and o["short_label"]


def test_short_name_pys_issuer():
    assert short_name("AZİMUT PYŞ KISA VADELİ BORÇLANMA ARAÇLARI FONU") == ("Azimut PYŞ", "KV Borçlanma")


def test_narrator_name_forms_accept_every_issuer_word():
    """The narrator's short-name check uses the same issuer words (a PYŞ label crashed it)."""
    from rmprep.narrator.validator import name_forms
    forms = name_forms("AZİMUT PYŞ KISA VADELİ BORÇLANMA ARAÇLARI FONU")
    assert "azimut pyş kv borçlanma" in forms and "azimut kv borçlanma" in forms
    assert name_forms("NUROL PORTFÖY PARA PİYASASI (TL) FONU")
