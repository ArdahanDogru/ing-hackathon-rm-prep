"""D23 analysis (docs/decision.md section 13; run in prototype/: python scripts/analysis/varlik_impact.py <snapshot>): current asset class (D19 rules) vs the majority class of the
real holdings (varlikData), for every fund of one snapshot. Read only."""
import collections
import glob
import gzip
import json
import re
import sys

from rmprep.decision import load_config
from rmprep.decision.universe import asset_class
from rmprep.ingest.pipeline import build_evidence

SNAP = sys.argv[1]
CLASS = {
    "nakit_benzeri": ["Ters-Repo", "Repo", "Mevduat (TL)", "Katılma Hesabı (TL)", "Takasbank Para Piyasası",
                      "Borsa İstanbul Para Piyasası", "BİST Taahhütlü İşlem Pazarı Alım",
                      "BİST Taahhütlü İşlem Pazarı Satım"],
    "borclanma": ["Devlet Tahvili", "Hazine Bonosu", "Özel Sektör Tahvili", "Finansman Bonosu",
                  "Özel Sektör Kira Sertifikaları", "Kamu Kira Sertifikaları (TL)",
                  "Varlığa Dayalı Menkul Kıymetler"],
    "hisse": ["Hisse Senedi", "Yabancı Hisse Senedi", "Yabancı Borsa Yatırım Fonları"],
    "altin_doviz": ["Kıymetli Madenler", "Kıymetli Madenler Cinsinden BYF",
                    "Kıymetli Madenler Cinsinden İhraç Edilen Kamu Kira Sertifikaları",
                    "Kıymetli Madenler Cinsinden İhraç Edilen Kamu Borçlanma Araçları",
                    "Mevduat (Döviz)", "Mevduat (Altın)", "Katılma Hesabı (Altın)", "Katılma Hesabı (Döviz)",
                    "Özel Sektör Dış Borçlanma Araçları", "Kamu Dış Borçlanma Araçları",
                    "Yabancı Özel Sektör Borçlanma Araçları", "Yabancı Kamu Borçlanma Araçları",
                    "Döviz Cinsi Kamu İç Borçlanma Araçları", "Kamu Kira Sertifikaları (Döviz)",
                    "Özel Sektör Yurt Dışı Kira Sertifikaları", "Kamu Yurt Dışı Kira Sertifikaları"],
    "fon": ["Yatırım Fonları Katılma Payları", "Borsa Yatırım Fonları Katılma Payları",
            "Girişim Sermayesi Yatırım Fonları Katılma Payları", "Gayrimenkul Yatırım Fonları Katılma Payları"],
    "ignore": ["Diğer", "Vadeli İşlemler Nakit Teminatları"],
}


def fold(s: str) -> str:
    """ASCII letters and digits only: the page has broken Turkish letters (U+FFFD)."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


LOOKUP = {fold(lab): cls for cls, labs in CLASS.items() for lab in labs}
assert len(LOOKUP) == sum(len(v) for v in CLASS.values()), "fold collision"


def holdings(code):
    f = f"data/snapshots/{SNAP}/payloads/tefas_detail/{code}.html.gz"
    try:
        t = gzip.open(f).read().decode("utf-8").replace('\\"', '"')
    except FileNotFoundError:
        return None
    m = re.search(r'"varlikData":(\[.*?\])', t)
    return json.loads(m.group(1)) if m else None


def majority(rows):
    shares = collections.Counter()
    for r in rows:
        cls = LOOKUP.get(fold(r["kiymetTip"]))
        if cls is None:
            raise KeyError(r["kiymetTip"])
        if cls != "ignore" and (r["portfoyOrani"] or 0) > 0:
            shares[cls] += r["portfoyOrani"]
    total = sum(shares.values())
    if not total:
        return None, {}
    pct = {c: 100 * v / total for c, v in shares.items()}
    top, top_pct = max(pct.items(), key=lambda kv: kv[1])
    return (top if top_pct >= 50 else "dengeli"), pct


cfg = load_config("config/decision.yaml")
kinds = cfg.raw["fund_kinds"]
fxw = cfg.raw["fx_name_words"]
ev = build_evidence("data/snapshots", SNAP)
risk = {d.entity: d.value for d in ev.datapoints if d.quantity == "fund_risk_level" and d.value}
change = collections.Counter()
examples = collections.defaultdict(list)
no_data = 0
for code, info in sorted(ev.entities.items()):
    fk = kinds.get(info.category)
    if fk is None:
        continue
    fx = any(w in info.name.upper() for w in fxw)
    cur = asset_class("fund", fk, info.name, fx, cfg, risk.get(code))
    rows = holdings(code)
    if not rows:
        no_data += 1
        continue
    new, pct = majority(rows)
    if new == "fon" or new is None:
        new = cur + " (fon: keep)"
    if fk == "money_market":
        new = "nakit_benzeri (umbrella)"
    key = (cur, new.split(" ")[0])
    change[key] += 1
    if key[0] != key[1] and len(examples[key]) < 3:
        examples[key].append(f"{code} {info.name[:38]} " + ", ".join(f"{c} {v:.0f}" for c, v in sorted(pct.items(), key=lambda kv: -kv[1])[:3]))
print("funds without holdings data:", no_data)
same = sum(n for (a, b), n in change.items() if a == b)
print("same class:", same, " different:", sum(change.values()) - same)
for (a, b), n in sorted(change.items(), key=lambda kv: -kv[1]):
    if a != b:
        print(f"{n:4d}  {a:>14} -> {b}")
        for e in examples[(a, b)]:
            print("        ", e.encode("ascii", "replace").decode())
