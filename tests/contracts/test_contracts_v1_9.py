"""Contract v1.9 (2026-10-14): option kinds etf and stock (docs/decision.md
section 16, D26); rm_edits "" = a deleted block (docs/narrator.md N14)."""

import pytest

from rmprep.contracts import OPTION_KINDS, ProductOption


def test_new_kinds():
    assert {"etf", "stock"} <= set(OPTION_KINDS)
    etf = ProductOption("etf:BOE", "etf", "AK PORTFÖY BIST 30 ENDEKSİ HSY BYF", entity="BOE", asset_class="hisse")
    stock = ProductOption("stock:THYAO", "stock", "TURK HAVA YOLLARI", entity="THYAO", asset_class="hisse")
    assert etf.kind == "etf" and stock.kind == "stock"
    assert ProductOption("etf:USD", "etf", "DOLAR BYF", entity="USD", fx=True).fx


@pytest.mark.parametrize("kind", ["etf", "stock"])
def test_etf_and_stock_have_no_fund_kind(kind):
    with pytest.raises(ValueError, match=f"{kind} option"):
        ProductOption(f"{kind}:X", kind, "X", fund_kind="equity")


def test_a_stock_has_no_fx_tag():
    with pytest.raises(ValueError, match="stock option"):
        ProductOption("stock:X", "stock", "X", fx=True)
