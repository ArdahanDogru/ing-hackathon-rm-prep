import json
from pathlib import Path

import pytest

from rmprep.contracts import Persona
from rmprep.research.checks import REASONS, check_question

FIX = Path(__file__).resolve().parents[1] / "contracts" / "fixtures" / "personas"
P01 = Persona.from_dict(json.loads((FIX / "p01.json").read_text(encoding="utf-8")))
WORDS = ("müşteri", "client", "customer")


def check(q, lang="TR"):
    return check_question(q, P01, lang, WORDS, 300)


@pytest.mark.parametrize("q", ["Nurol Portföy son haberler",
                               "Ak Portföy hakkında yeni bir haber var mı?",
                               "PPN fonunun yönetim ücreti ne kadar?"])
def test_product_questions_pass(q):
    assert check(q) is None


def test_empty_and_long():
    assert check("   ") == REASONS["TR"]["empty"]
    assert check("x" * 301) == "Soru 300 karakterden uzun."
    assert check("x" * 300) is None


@pytest.mark.parametrize("q", [
    "Müşterim için PPN uygun mu?",
    "MÜŞTERİM için PPN uygun mu?",                       # Turkish upper case
    "Müşterinin parası nereye gitmeli?",
    "Is PPN right for my client?",
    f"{P01.yas} yaşında biri için PPN uygun mu?",         # the persona's age
    "TL mevduat ağırlıklı portföyler için para piyasası fonu",  # 3 words of `durum`
    "Mevcut portföyün mevduat yoğunluğunu azaltacak fon",  # 3 words of `rm_notu`
])
def test_client_data_is_refused(q):
    assert check(q) == REASONS["TR"]["client"]


def test_reason_in_english():
    assert check("my client", "EN") == "The question contains client information; ask only about products or companies."
