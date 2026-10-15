"""Mockups of the card "Mevcut ve hedef dağılım" (W18 v2, 2026-10-15): three
variants A, B, C, each with all five classes, first with the pop-up notes closed,
then open. Real P01 values (snapshot 20261014-233110-1565). Writes
allocation-v2-A.html, -B.html, -C.html next to this file.

    python docs/web-ui/mockups/allocation_v2.py
"""
from pathlib import Path

HERE = Path(__file__).parent

# class, label, current, range, source kind, source line, band, best option, best detail, best colour
ROWS = [
    ("nakit_benzeri", "Nakit benzeri", 75.0, (60, 90), "act",
     'müşteri dosyası, "Varlığı TL mevduat ağırlıklı" → %60–90', (10, 20),
     "Nurol Portföy Para Piyasası (TL)", "reel +%7,4 · risk 1/7", "#027A48"),
    ("borclanma", "Borçlanma", 8.1, (3.1, 13.1), "est",
     "Emekli profili (varsayım; ulusal ortalamadan, hisse daha az, borçlanma daha çok)", (60, 70),
     "Osmanlı Portföy Özel Sektör Borçlanma", "reel +%7,8 · risk 1/7", "#027A48"),
    ("hisse", "Hisse", 3.7, (0, 8.7), "est", "Emekli profili (varsayım)", (10, 20),
     None, "Risk tavanı nedeniyle uygun fon yok.", "#667085"),
    ("altin_doviz", "Altın / döviz", 9.5, (4.5, 14.5), "est", "Emekli profili (varsayım)", (5, 10),
     "Kuveyt Türk Altın Katılım", "son 1 yıl reel −%12,9: önerilmiyor", "#B42318"),
    ("dengeli", "Dengeli", 3.7, (0, 8.7), "est", "Emekli profili (varsayım)", None,
     "Kuveyt Türk Çoklu Varlık Katılım", "reel +%8,4 · risk 2/7", "#027A48"),
]
COLORS = {"nakit_benzeri": "#1F3A68", "borclanma": "#6172F3", "hisse": "#12B76A",
          "altin_doviz": "#F79009", "dengeli": "#98A2B3"}
SOURCE = ("Kaynak: Ata Yatırım, \"Risk Profillerine Göre Örnek Portföy Yapıları\", 28.04.2026. "
          "Gösterge niteliğinde stratejik bant; ING'nin model portföyü değildir.")

CSS = """
:root{--ink:#1D2939;--muted:#667085;--line:#EAECF0;--bg:#F7F7F5;--navy:#1F3A68;--est:#98A2B3;
--over:#B42318;--under:#027A48}
*{box-sizing:border-box}body{margin:0;padding:24px;background:var(--bg);
font-family:Inter,system-ui,Segoe UI,sans-serif;color:var(--ink)}
h1{font-size:19px;margin:0 0 4px}.lead{color:var(--muted);margin:0 0 18px;font-size:13px;max-width:900px}
h2{font-size:15px;margin:22px 0 8px}
.card{background:#fff;border-radius:16px;box-shadow:0 1px 3px rgba(16,24,40,.08);padding:20px 22px;width:900px;position:relative}
.title{font-weight:700;font-size:16px;margin:0}
.head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.summary{background:#F2F4F7;border-radius:10px;padding:10px 12px;font-size:14px;line-height:1.45;margin-bottom:10px}
.banner{border:1px solid var(--line);border-radius:10px;padding:8px 12px;font-size:13px;color:#475467;margin-bottom:6px}
.row{display:grid;grid-template-columns:150px 290px 175px 1fr;gap:14px;align-items:center;padding:12px 0 4px;border-top:1px solid var(--line);position:relative}
.cls{font-weight:700;font-size:15px;display:flex;align-items:center;gap:6px}
.src{grid-column:1/span 4;font-size:12px;color:var(--muted);padding-bottom:6px}
.track{position:relative;height:22px;background:#F2F4F7;border-radius:6px}
.range{position:absolute;top:10px;height:2px;background:#344054}
.mark{position:absolute;top:2px;width:4px;height:18px;border-radius:2px;transform:translateX(-2px)}
.act{background:var(--navy)}.est{background:var(--est)}
.scale{display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:2px}
.val{font-size:14px}.val b{font-size:16px}.rng{color:var(--muted)}
.badge{display:inline-block;font-size:11px;font-weight:700;border-radius:999px;padding:2px 8px;margin-top:3px}
.b-act{background:#E0EAFF;color:var(--navy)}.b-est{background:#F2F4F7;color:#475467}
.gap{font-size:12px;font-weight:700;margin-top:3px}.over{color:var(--over)}.under{color:var(--under)}
.in{color:var(--muted);font-weight:500}.link{text-decoration:underline dotted;cursor:pointer}
.best .t{font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);font-weight:700}
.best .n{font-weight:700;font-size:14px}.best .s{font-size:12px}
.legend{display:flex;gap:18px;font-size:12px;color:var(--muted);margin-top:8px;border-top:1px solid var(--line);padding-top:10px;flex-wrap:wrap}
.legend i{display:inline-block;vertical-align:middle;margin-right:5px}
.btns{display:flex;gap:8px;margin-top:12px}.btn{border:1px solid #D0D5DD;background:#fff;border-radius:10px;padding:7px 14px;font-weight:700;font-size:13px}
.primary{background:var(--navy);color:#fff;border-color:var(--navy)}
.i{display:inline-flex;width:18px;height:18px;border-radius:50%;border:1.5px solid #98A2B3;color:#475467;font-size:11px;font-weight:800;align-items:center;justify-content:center;cursor:pointer}
.i.on{border-color:var(--navy);color:var(--navy);background:#E0EAFF}
.pill{display:inline-block;border:1px solid #D0D5DD;border-radius:999px;padding:4px 11px;font-size:12px;font-weight:700;cursor:pointer;background:#fff}
.pill.on{border-color:var(--navy);background:#E0EAFF;color:var(--navy)}
.note{position:absolute;z-index:5;background:#fff;border:1px solid var(--line);border-radius:12px;box-shadow:0 10px 28px rgba(16,24,40,.16);padding:12px 14px;font-size:13px;line-height:1.45}
.note h4{margin:0 0 6px;font-size:13px}.note small{color:var(--muted)}.x{float:right;color:var(--muted);font-weight:700}
.band{position:relative;height:16px;background:#F2F4F7;border-radius:5px;margin:8px 0 2px}
.band .area{position:absolute;top:0;bottom:0;background:#C7D7FE;border-radius:5px}
.band .mark{top:-1px;height:18px}
.stack{display:flex;height:30px;border-radius:8px;overflow:hidden;margin:4px 0 6px}
.stack div{display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px;font-weight:700;white-space:nowrap;overflow:hidden}
.stacklbl{display:flex;gap:14px;font-size:12px;color:#475467;flex-wrap:wrap;margin-bottom:6px}
.stacklbl i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle}
table.tgt{border-collapse:collapse;width:100%;font-size:13px;margin:4px 0 6px}
table.tgt td,table.tgt th{padding:5px 6px;border-top:1px solid var(--line);text-align:left}
table.tgt th{font-size:11px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.mini{position:relative;height:10px;width:110px;background:#F2F4F7;border-radius:3px;display:inline-block;vertical-align:middle}
.mini .area{position:absolute;top:0;bottom:0;background:#C7D7FE;border-radius:3px}
.mini .mark{position:absolute;top:-2px;width:3px;height:14px;border-radius:1px;transform:translateX(-1px)}
"""


def pct(x):
    return f"%{x:.0f}" if x is not None else "—"


def gap_of(cur, band):
    if band is None:
        return None
    lo, hi = band
    return lo - cur if cur < lo else (hi - cur if cur > hi else 0.0)


def gap_text(g):
    if g is None:
        return '<div class="gap in">hedef bant yok</div>', "in"
    if g > 0:
        return f'<div class="gap under">hedefin {g:.0f} puan altında</div>', "under"
    if g < 0:
        return f'<div class="gap over">hedefin {-g:.0f} puan üstünde</div>', "over"
    return '<div class="gap in">hedef bandın içinde</div>', "in"


def track(cur, rng, kind):
    lo, hi = rng
    return (f'<div><div class="track"><div class="range" style="left:{lo}%;width:{hi - lo}%"></div>'
            f'<div class="mark {kind}" style="left:{cur}%"></div></div>'
            f'<div class="scale"><span>0</span><span>50</span><span>100 %</span></div></div>')


def best(name, detail, colour):
    head = '<div class="t">Bu sınıfta en iyi seçenek</div>'
    if name is None:
        return f'<div class="best">{head}<div class="s" style="color:{colour};font-size:13px">{detail}</div></div>'
    return (f'<div class="best">{head}<div class="n">{name}</div>'
            f'<div class="s" style="color:{colour}">{detail}</div></div>')


def class_note(label, cur, band, kind, width=320):
    """The pop-up note of one class (variants A and C)."""
    if band is None:
        body = ("<p style='margin:0'>Dengeli (çoklu varlık) fonlar bir fon türüdür, varlık sınıfı değildir; "
                "model portföyde ayrı bir bandı yoktur.</p>")
        return f'<h4>{label} · hedef bant yok <span class="x">✕</span></h4>{body}'
    lo, hi = band
    g = gap_of(cur, band)
    rel = ("hedef bandın içinde" if g == 0 else
           f"hedefin <b>{abs(g):.0f} puan {'altında' if g > 0 else 'üstünde'}</b>")
    return (f'<h4>{label} · Muhafazakâr hedef: %{lo}–{hi} <span class="x">✕</span></h4>'
            f'<div class="band"><div class="area" style="left:{lo}%;width:{hi - lo}%"></div>'
            f'<div class="mark {kind}" style="left:{cur}%"></div></div>'
            f'<small>0 · · · · 50 · · · · 100 % &nbsp; açık alan: hedef bant · işaret: mevcut pay</small>'
            f'<p style="margin:8px 0 0">Mevcut {pct(cur)}{" (tahmin)" if kind == "est" else ""}, {rel}.</p>'
            f'<p style="margin:6px 0 0"><small>{SOURCE}</small></p>')


SUMMARY = ('<div class="summary">Tahmine göre müşterinin parası çoğunlukla <b>nakit benzeri</b> '
           '(%75; müşteri dosyasından). Muhafazakâr hedefte bu oran %10–20. Bu yüzden '
           '<b>borçlanma</b> fonları öne çıkıyor.</div>')
BANNER = ('<div class="banner">Nakit benzeri payı müşteri dosyasından; diğer sınıflar tahmini '
          'senaryodur ve sıralamayı etkilemez.</div>')
BUTTONS = '<div class="btns"><span class="btn primary">Tahmini onayla</span><span class="btn">Düzenle</span></div>'


def legend(extra=""):
    return ('<div class="legend"><span><i style="width:4px;height:14px;background:var(--navy)"></i>'
            'mevcut pay (RM veya müşteri dosyası)</span><span><i style="width:4px;height:14px;'
            'background:var(--est)"></i>mevcut pay (tahmin)</span><span><i style="width:18px;height:2px;'
            f'background:#344054"></i>tahminin aralığı</span>{extra}</div>')


def stack():
    segs = "".join(
        f'<div style="width:{cur}%;background:{COLORS[c]}">{label.split()[0] + " " + pct(cur) if cur >= 10 else ""}</div>'
        for c, label, cur, *_ in ROWS)
    lbls = "".join(
        f'<span><i style="background:{COLORS[c]}"></i>{label} {pct(cur)} · '
        f'{"müşteri dosyası" if kind == "act" else "tahmin"}</span>'
        for c, label, cur, _r, kind, *_ in ROWS)
    return (f'<div style="font-size:12px;font-weight:700;color:#475467">Tahmini mevcut portföy</div>'
            f'<div class="stack">{segs}</div><div class="stacklbl">{lbls}</div>')


def target_table():
    rows = []
    for c, label, cur, _r, kind, _s, band, *_ in ROWS:
        g = gap_of(cur, band)
        gt, cls = gap_text(g)
        mini = ("" if band is None else
                f'<span class="mini"><span class="area" style="left:{band[0]}%;width:{band[1] - band[0]}%"></span>'
                f'<span class="mark {kind}" style="left:{cur}%"></span></span>')
        rows.append(f'<tr><td>{label}</td><td>{"%" + str(band[0]) + "–" + str(band[1]) if band else "—"}</td>'
                    f'<td>{pct(cur)}{" (tahmin)" if kind == "est" else ""}</td><td>{mini}</td>'
                    f'<td class="{cls}" style="font-weight:700;font-size:12px">{gt[gt.index(">") + 1:gt.rindex("<")]}</td></tr>')
    return ('<h4>Hedef dağılım · Muhafazakâr <span class="x">✕</span></h4>'
            '<table class="tgt"><tr><th>Sınıf</th><th>Hedef</th><th>Mevcut</th><th>Hedef bant · mevcut</th><th>Fark</th></tr>'
            + "".join(rows) + f'</table><small>{SOURCE}</small>')


def rows_html(variant, open_notes=frozenset()):
    out = []
    for c, label, cur, rng, kind, src, band, name, detail, colour in ROWS:
        gt, _ = gap_text(gap_of(cur, band))
        badge = ('<span class="badge b-act">müşteri dosyası</span>' if kind == "act"
                 else '<span class="badge b-est">tahmini senaryo</span>')
        rng_txt = f'<span class="rng">({rng[0]:.0f}–{rng[1]:.0f})</span>'
        note = ""
        cls_cell = f'<div class="cls">{label}</div>'
        if variant == "A":
            on = c in open_notes
            cls_cell = f'<div class="cls">{label} <span class="i{" on" if on else ""}">i</span></div>'
            if on:
                note = f'<div class="note" style="left:40px;top:44px;width:340px">{class_note(label, cur, band, kind)}</div>'
        if variant == "C":
            gt = gt.replace('class="gap ', 'class="gap link ').replace("</div>", " ▾</div>")
            if c in open_notes:
                note = f'<div class="note" style="left:470px;top:70px;width:330px">{class_note(label, cur, band, kind)}</div>'
        out.append(f'<div class="row">{cls_cell}{track(cur, rng, kind)}'
                   f'<div class="val">Mevcut <b>{pct(cur)}</b> {rng_txt}<br>{badge}{gt}</div>'
                   f'{best(name, detail, colour)}<div class="src">Kaynak: {src}</div>{note}</div>')
    return "".join(out)


def card(variant, open_notes=frozenset(), table_open=False):
    head_right = ""
    if variant == "B":
        head_right = f'<span class="pill{" on" if table_open else ""}">ⓘ Hedef dağılım (Muhafazakâr)</span>'
    parts = [f'<div class="card"><div class="head"><p class="title">Mevcut ve hedef dağılım</p>{head_right}</div>',
             SUMMARY, BANNER]
    if variant == "B":
        parts.append(stack())
    parts.append(rows_html(variant, open_notes))
    extra = {"A": '<span><span class="i">i</span> hedef bant (tıklayın)</span>',
             "B": '<span>ⓘ Hedef dağılım: tüm sınıfların hedef bandı</span>',
             "C": '<span>▾ fark metnine tıklayın: hedef bant</span>'}[variant]
    parts += [legend(extra), BUTTONS]
    if variant == "B" and table_open:
        parts.append(f'<div class="note" style="right:18px;top:52px;width:560px">{target_table()}</div>')
    parts.append("</div>")
    return "".join(parts)


TITLES = {
    "A": ("A · Her sınıfın yanında ⓘ: o sınıfın hedef bandı açılır not olarak",
          "En az değişiklik. Hedef yalnızca ⓘ tıklanınca görünür; her not tek sınıfı gösterir."),
    "B": ("B · Üstte tahmini portföy tek çubukta; tüm hedefler tek bir 'Hedef dağılım' notunda",
          "Tahmini portföy en görünür bölüm. Hedef, fark ve kaynak tek tabloda; satırlarda ⓘ yok."),
    "C": ("C · Fark metni tıklanınca o sınıfın hedef bandı açılır",
          "Hedef yalnızca RM farkı merak edince görünür; fark metni bağlantıdır."),
}


def page(variant):
    title, lead = TITLES[variant]
    blocks = [f"<h1>{title}</h1><p class='lead'>{lead} P01 · Emekli girişimci · Muhafazakâr · "
              "gerçek değerler (snapshot 20261014-233110-1565).</p>",
              "<h2>1 · Notlar kapalı</h2>", card(variant)]
    if variant == "A":
        blocks += ["<h2>2 · Nakit benzeri ⓘ açık</h2>", card("A", {"nakit_benzeri"}),
                   "<h2>3 · Borçlanma ⓘ açık (tahmin satırı)</h2>", card("A", {"borclanma"}),
                   "<h2>4 · Dengeli ⓘ açık (hedef bant yok)</h2>", card("A", {"dengeli"})]
    elif variant == "B":
        blocks += ["<h2>2 · 'Hedef dağılım' notu açık</h2>", card("B", table_open=True)]
    else:
        blocks += ["<h2>2 · Nakit benzeri fark notu açık</h2>", card("C", {"nakit_benzeri"}),
                   "<h2>3 · Borçlanma fark notu açık (tahmin satırı)</h2>", card("C", {"borclanma"})]
    return (f'<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8"><title>{title}</title>'
            f"<style>{CSS}</style></head><body>{''.join(blocks)}</body></html>")


if __name__ == "__main__":
    for v in "ABC":
        (HERE / f"allocation-v2-{v}.html").write_text(page(v), encoding="utf-8")
        print("wrote", HERE / f"allocation-v2-{v}.html")
