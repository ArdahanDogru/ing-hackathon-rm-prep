"""UI labels in Turkish and English (docs/ui.md section 4). Every key has both
languages. Engine texts (reasons, warnings, questions) are not here: they are
Turkish only and are shown as they are."""

from __future__ import annotations

LANGS = ("TR", "EN")

LABELS: dict[str, dict[str, str]] = {
    "title": {"TR": "Görüşme hazırlığı", "EN": "Meeting preparation"},
    "persona": {"TR": "Müşteri (persona)", "EN": "Client (persona)"},
    "snapshot": {"TR": "Veri anlık görüntüsü", "EN": "Data snapshot"},
    "sources": {"TR": "Kaynaklar (☑ = kullanılır)", "EN": "Sources (☑ = used)"},
    "fallback_from": {"TR": "yedek: {snapshot}", "EN": "fallback: {snapshot}"},
    "state_ready": {"TR": "Hazır: seçenekler sıralandı.", "EN": "Ready: options are ranked."},
    "state_needs_input": {"TR": "Önce soruları yanıtlayın.",
                          "EN": "Önce soruları yanıtlayın. (Answer the questions first.)"},
    "run": {"TR": "Çalıştırma", "EN": "Run"},
    "rm_status": {"TR": "RM durumu", "EN": "RM status"},
    "excluded": {"TR": "Hariç kaynaklar", "EN": "Excluded sources"},
    "issues": {"TR": "Olası sorunlar", "EN": "Possible issues"},
    "coming_later": {"TR": "Bu bölüm sonraki adımda gelecek.",
                     "EN": "This part comes in a later step."},
    # persona fields (schema names stay Turkish in the data)
    "f_persona_id": {"TR": "Persona", "EN": "Persona"},
    "f_profil": {"TR": "Profil", "EN": "Profile"},
    "f_yas": {"TR": "Yaş", "EN": "Age"},
    "f_risk_profili": {"TR": "Risk profili", "EN": "Risk profile"},
    "f_durum": {"TR": "Durum", "EN": "Situation"},
    "f_yatirim_amaci": {"TR": "Yatırım amacı", "EN": "Investment goal"},
    "f_yatirim_ufku": {"TR": "Yatırım ufku", "EN": "Investment horizon"},
    "f_likidite_ihtiyaci": {"TR": "Likidite ihtiyacı", "EN": "Liquidity need"},
    "f_doviz_maruz_kalma_tercihi": {"TR": "Döviz maruziyeti tercihi", "EN": "FX exposure preference"},
    "f_gelir_nakit_akisi_ihtiyaci": {"TR": "Gelir / nakit akışı ihtiyacı",
                                     "EN": "Income / cash-flow need"},
    "f_anapara_koruma_tercihi": {"TR": "Anapara koruma tercihi", "EN": "Capital protection preference"},
    "f_oncelikler": {"TR": "Öncelikler", "EN": "Priorities"},
    "f_acik_kisitlar": {"TR": "Açık kısıtlar", "EN": "Explicit constraints"},
    "f_rm_notu": {"TR": "RM notu", "EN": "RM note"},
}


def t(key: str, lang: str = "TR", **fmt: object) -> str:
    text = LABELS[key][lang]
    return text.format(**fmt) if fmt else text
