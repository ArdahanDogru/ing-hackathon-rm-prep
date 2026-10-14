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


def test_a_decomposed_word_is_refused_as_the_composed_one():
    nfd = "mu" + "\u0308" + "s" + "\u0327" + "terim için PPN uygun mu?"      # müşterim, NFD
    assert nfd != "müşterim için PPN uygun mu?"
    assert check(nfd) == REASONS["TR"]["client"]
    assert check_question(nfd.replace("mu\u0308", "mü"), P01, "TR", WORDS, 300) == REASONS["TR"]["client"]
    # the client words themselves may be decomposed too
    assert check_question("müşterim için PPN", P01, "TR", ("mu\u0308s\u0327teri",), 300) == REASONS["TR"]["client"]
