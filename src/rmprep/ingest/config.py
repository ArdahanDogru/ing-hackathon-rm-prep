"""Load and validate config/sources.yaml.

`load_raw` reads the YAML; `parse_config` validates a plain dict. The raw dict
is what goes into the snapshot manifest, so replay calls `parse_config` on the
manifest copy and never re-reads the file.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml

CONFIG_VERSION = 1
ADAPTERS = ("evds", "tefas", "tefas_web", "tefas_detail", "manual", "bist_bulletin", "ing_web",
            "bank_table")
TEFAS_WEB_HOST = "www.tefas.gov.tr"
BIST_HOST = "www.borsaistanbul.com"
ING_HOST = "www.ing.com.tr"
ING_LAYOUTS = ("grid", "balance")
# I11: the quantities the bist_bulletin adapter writes; each must be in `quantities`.
BIST_QUANTITIES = ("stock_close", "stock_return_1m", "stock_return_3m", "stock_return_6m",
                   "stock_return_1y", "stock_volatility_1y", "stock_turnover_3m",
                   "stock_bist100")
# tefas.gov.tr/robots.txt (2026-10-09) disallows these paths for all agents.
TEFAS_DISALLOWED_PREFIXES = ("/api/", "/private/", "/tefasbuild", "/_next/", "/static/")
ON_FAILURE = ("previous", "exclude")
FREQUENCIES = ("daily", "weekly", "monthly")
VERIFY_PREFIX = "VERIFY_"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


class ConfigError(ValueError):
    """Invalid configuration. The message starts with the path of the bad key."""


@dataclass(frozen=True)
class Quantity:
    name: str
    unit: str
    max_age_days: int
    min: float
    max: float
    conflict_tolerance: float


@dataclass(frozen=True)
class AnnualChange:
    """I5: the 12-month change of a monthly index series, as its own quantity."""
    quantity: str
    entity: str


@dataclass(frozen=True)
class EvdsSeries:
    code: str
    quantity: str
    entity: str
    frequency: Literal["daily", "weekly", "monthly"]
    verified: bool
    lookback_days: int | None = None           # None -> the source's lookback_days
    annual_change: AnnualChange | None = None

    @property
    def is_placeholder(self) -> bool:
        return self.code.startswith(VERIFY_PREFIX)


@dataclass(frozen=True)
class SourceConfig:
    name: str
    adapter: str
    enabled: bool
    on_failure: Literal["previous", "exclude"]
    source_url: str
    tos_note: str


@dataclass(frozen=True)
class EvdsSource(SourceConfig):
    base_url: str
    api_key_env: str
    lookback_days: int
    timeout_seconds: float
    series: tuple[EvdsSeries, ...]


@dataclass(frozen=True)
class TefasSource(SourceConfig):
    inbox: str
    file_patterns: tuple[str, ...]
    date_column: str
    entity_column: str
    column_aliases: dict[str, tuple[str, ...]]
    value_columns: dict[str, str]


@dataclass(frozen=True)
class TefasWebSource(SourceConfig):
    url: str
    user_agent: str
    timeout_seconds: float
    min_funds: int
    value_fields: dict[str, str]     # field in the page data -> quantity
    flag_needs_check: bool


_TR_LOWER = str.maketrans("İI", "iı")


def normalize_status(text: str) -> str:
    """Status text key: Turkish lower case ("İ" -> "i", "I" -> "ı"), spaces
    collapsed, trimmed."""
    return " ".join(text.translate(_TR_LOWER).lower().split())


@dataclass(frozen=True)
class StatusMap:
    """A text field of the page mapped to a 0/1 quantity (I3b: tefasDurum ->
    fund_buyable). Keys are normalize_status() of the texts."""
    field: str                       # "profilData.tefasDurum"
    quantity: str
    map: dict[str, float]


@dataclass(frozen=True)
class TefasDetailSource(SourceConfig):
    url: str                         # with "{code}" for the fund code
    user_agent: str
    timeout_seconds: float
    min_interval_s: float            # at least this many seconds between requests
    max_fail_share: float            # more failed pages -> the source fails
    max_funds: int | None            # limit for tests and trials
    funds_from: tuple[str, ...]      # tefas_web sources that give the fund list (I10: several)
    exclude_categories: tuple[str, ...]
    value_fields: dict[str, str]     # "bilgiData.<field>" -> quantity; required
    optional_fields: dict[str, str]  # same, but no value -> no row
    flag_needs_check: bool
    status: StatusMap | None = None
    holdings_quantity: str | None = None   # I8: varlikData rows; None -> no holdings rows

    def page_url(self, code: str) -> str:
        return self.url.replace("{code}", code)


DETAIL_OBJECTS = ("bilgiData", "profilData")


@dataclass(frozen=True)
class BistBulletinSource(SourceConfig):
    """I11: Borsa İstanbul end-of-day bulletins, one ZIP per trading day."""
    url: str                         # with {yyyy}, {mm}, {yyyymmdd}
    user_agent: str
    timeout_seconds: float
    history_days: int                # days of bulletins used (the first run fetches them all)
    min_interval_s: float            # at least this many seconds between requests
    recheck_days: int                # a day without a bulletin this recent is asked again
    min_shares: int                  # fewer shares with a close -> the file is not valid
    adjust_jump_pct: float = 10.5    # I11b: a close move beyond ± this % = corporate action
    price_limit_pct: float = 10.0    # I11c: daily price limit, bounds the base price

    def day_url(self, day: date) -> str:
        return self.url.format(yyyy=f"{day:%Y}", mm=f"{day:%m}", yyyymmdd=f"{day:%Y%m%d}")


@dataclass(frozen=True)
class IngForm:
    """I14: the field names and values of the ASP.NET rate form (config, not code)."""
    currency_field: str              # "5575$DdlCurrencyType"; also the postback target of step 2
    product_field: str               # "5575$DdlProductList"
    send_target: str                 # "5575$BtnSend", the postback target of step 3
    currency: str                    # "0" = TL
    no_product: str                  # "-1" = no product chosen (step 2)


@dataclass(frozen=True)
class IngProduct:
    value: str                       # the product value in the form, e.g. E_TIME_DEPOSIT_ACCOUNT
    layout: Literal["grid", "balance"]
    entity: str                      # grid: {row}, {column}; balance: {rate}, {balance}
    min_rows: int
    min_columns: int                 # value columns, without the row label column
    balance_header: str = ""         # balance: the first header cell
    no_interest_column: str = ""     # balance: the column of the amount without interest;
                                     # "" = the table has no such column (I14b)
    rates: dict[str, str] | None = None             # balance: rate column -> word in the entity
    balance_labels: dict[str, str] | None = None    # balance: page label -> name text


@dataclass(frozen=True)
class IngWebSource(SourceConfig):
    url: str
    user_agent: str
    timeout_seconds: float
    delay_seconds: float             # at least this long between two requests
    quantity: str
    form: IngForm
    products: tuple[IngProduct, ...]


# ing.com.tr/robots.txt (checked 2026-10-16): Disallow /documents/*, /objects/*,
# /assets/* (but Allow their .css/.js, and images under /assets/), /*-tamam$,
# /*-hata$, /*?IsPreview=1$, /*-mim$, /*-mim?*, /*-kaydet-ve-cik$, /error-page,
# /hata-sayfasi, /*1000$, */search/, */arama/.
_ING_ALLOWED_EXT = {"/documents/": {"css", "js"}, "/objects/": {"css", "js"},
                    "/assets/": {"css", "js", "png", "jpg", "jpeg", "gif", "svg", "webp", "ico",
                                 "bmp"}}


def ing_robots_disallows(url: str) -> bool:
    parts = urlsplit(url)
    path = parts.path
    full = path + (f"?{parts.query}" if parts.query else "")
    for prefix, allowed in _ING_ALLOWED_EXT.items():
        if path.startswith(prefix):
            last = path.rsplit("/", 1)[-1]
            return not ("." in last and last.rsplit(".", 1)[-1].lower() in allowed)
    return (full.endswith(("-tamam", "-hata", "-mim", "-kaydet-ve-cik", "1000", "?IsPreview=1"))
            or "-mim?" in full or path.startswith(("/error-page", "/hata-sayfasi"))
            or "/search/" in path or "/arama/" in path)


@dataclass(frozen=True)
class BankTable:
    """I15: one rate table on a bank page, chosen by its exact header row."""
    header: tuple[str, ...]          # the row label cell, then the amount columns
    entity: str                      # with {row} and {column}
    decimal: Literal[",", "."]
    min_rows: int                    # rows after skip_rows
    skip_rows: tuple[str, ...] = ()  # row labels that are not terms
    note: str = ""


@dataclass(frozen=True)
class BankTableSource(SourceConfig):
    url: str
    user_agent: str
    timeout_seconds: float
    quantity: str
    tables: tuple[BankTable, ...]


# I15: the Disallow lines for "*" of each bank host (robots.txt read 2026-10-16).
# A bank_table source on a host that is not here is a config error.
BANK_ROBOTS_DISALLOW: dict[str, tuple[str, ...]] = {
    "www.isbank.com.tr": (
        "/_layouts/", "/_vti_bin/", "/_catalogs/", "/temp/", "/programs/", "/hidden",
        "/ru/search*", "/ru/_vti_bin/", "/en/_vti_bin/", "/TSPD*", "/arama/*",
        "/fiyatoran/FiyatTabloGoster.asp*", "/?tknfv*", "/*search.asmx*", "/?dsclosureid=*",
        "/?tribe-bar-date=*"),
    "www.ziraatbank.com.tr": (
        "/_layouts/", "/_vti_bin/", "/_catalogs/",
        "/tr/gecmisin-sahidi-gelecegin-sahibi-buyuk-ziraat-ailesi",
        "/tr/ziraat-katilim-10-yasinda", "/tr/bankamiz/basin-odasi/basin-bultenleri",
        "/tr/Sayfalar/ziraat-basketbol-turkiye-isim-sponsoru.aspx", "/tr/turkiye-kupasi-2202",
        "/tr/Sayfalar/genclik-caddesi-subemiz-acilisi.aspx", "/tr/25-yildir-gucumuz-teknoloji-2026",
        "/tr/bankamiz/ziraatten-duyurular/duyurular/kurban-bayrami-hizmet-veren-subeler-2026",
        "/tr/Bankamiz-ZB/ziraatten-duyurular/genel-duyurular/Documents/"
        "kurban-bayrami-subeler-2026.pdf",
        "/tr/Bankamiz-ZB/ziraatten-duyurular/genel-duyurular/Documents/"
        "kurban-bayrami-mobil-subeler-2026.pdf",
        "/tr/ziraat-ilk-balikci-fabrika-gemisi", "/tr/Bankamiz-ZB/basin-odasi/BasinBultenleri/",
        "/tr/1985-ayin-altin-adami-odulleri"),
}


def robots_disallows(patterns: tuple[str, ...], url: str) -> bool:
    """True if a Disallow pattern matches the path (+ query) of `url`: a prefix
    match, `*` = any text, `$` at the end = the end of the URL."""
    parts = urlsplit(url)
    target = parts.path + (f"?{parts.query}" if parts.query else "")
    for pattern in patterns:
        anchored = pattern.endswith("$")
        regex = ".*".join(re.escape(p) for p in pattern.rstrip("$").split("*"))
        if re.match(regex + ("$" if anchored else ""), target):
            return True
    return False


@dataclass(frozen=True)
class ManualSource(SourceConfig):
    inbox: str
    file_patterns: tuple[str, ...]
    allowed_quantities: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    quantities: dict[str, Quantity]
    sources: dict[str, SourceConfig]

    def enabled_sources(self) -> list[SourceConfig]:
        return [s for s in self.sources.values() if s.enabled]


def load_raw(path: str | Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    return raw


def load_config(path: str | Path) -> Config:
    return parse_config(load_raw(path))


_TR_FOLD = str.maketrans("İIıÇĞÖŞÜçğöşü", "iiicgosucgosu")


def normalize_header(name: str) -> str:
    """Header key for alias matching: trimmed, single spaces, lower case, Turkish
    letters folded to ASCII, so "FİYAT", "Fiyat" and "FIYAT" all match."""
    return " ".join(str(name).split()).translate(_TR_FOLD).lower()


# --- validation helpers --------------------------------------------------------

def _mapping(v: Any, path: str) -> dict[str, Any]:
    if not isinstance(v, dict):
        raise ConfigError(f"{path}: must be a mapping")
    return v


def _check_keys(d: dict[str, Any], path: str, required: set[str], optional: set[str]) -> None:
    missing = required - d.keys()
    if missing:
        raise ConfigError(f"{path}: missing key(s) {sorted(missing)}")
    unknown = d.keys() - required - optional
    if unknown:
        raise ConfigError(f"{path}: unknown key(s) {sorted(unknown)}")


def _str(v: Any, path: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ConfigError(f"{path}: must be a non-empty string")
    return v.strip()


def _bool(v: Any, path: str) -> bool:
    if not isinstance(v, bool):
        raise ConfigError(f"{path}: must be true or false")
    return v


def _num(v: Any, path: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{path}: must be a number")
    return float(v)


def _pos_int(v: Any, path: str) -> int:
    if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
        raise ConfigError(f"{path}: must be a positive integer")
    return v


def _choice(v: Any, path: str, choices: tuple[str, ...]) -> str:
    if v not in choices:
        raise ConfigError(f"{path}: must be one of {list(choices)}, got {v!r}")
    return v


def _str_list(v: Any, path: str) -> tuple[str, ...]:
    if not isinstance(v, list) or not v:
        raise ConfigError(f"{path}: must be a non-empty list")
    return tuple(_str(x, f"{path}[{i}]") for i, x in enumerate(v))


def _name(v: str, path: str) -> str:
    if not _NAME_RE.match(v):
        raise ConfigError(f"{path}: name {v!r} must match {_NAME_RE.pattern}")
    return v


# --- parsing --------------------------------------------------------------------

_COMMON_REQUIRED = {"adapter", "source_url", "tos_note"}
_COMMON_OPTIONAL = {"enabled", "on_failure"}


def parse_config(raw: dict[str, Any]) -> Config:
    raw = _mapping(raw, "config")
    _check_keys(raw, "config", {"version", "quantities", "sources"}, set())
    if raw["version"] != CONFIG_VERSION:
        raise ConfigError(f"version: expected {CONFIG_VERSION}, got {raw['version']!r}")

    quantities = {
        _name(name, f"quantities.{name}"): _parse_quantity(name, q)
        for name, q in _mapping(raw["quantities"], "quantities").items()
    }
    if not quantities:
        raise ConfigError("quantities: at least one quantity is required")

    sources: dict[str, SourceConfig] = {}
    for name, s in _mapping(raw["sources"], "sources").items():
        path = f"sources.{_name(name, f'sources.{name}')}"
        s = _mapping(s, path)
        adapter = _choice(s.get("adapter"), f"{path}.adapter", ADAPTERS)
        sources[name] = _PARSERS[adapter](name, s, path, quantities)
    if not sources:
        raise ConfigError("sources: at least one source is required")
    for name, src in sources.items():
        if not isinstance(src, TefasDetailSource):
            continue
        listed = isinstance(raw["sources"][name].get("funds_from"), list)
        for i, other in enumerate(src.funds_from):
            if not isinstance(sources.get(other), TefasWebSource):
                where = f"funds_from[{i}]" if listed else "funds_from"
                raise ConfigError(f"sources.{name}.{where}: must name a tefas_web source, "
                                  f"got {other!r}")
    return Config(quantities=quantities, sources=sources)


def _parse_quantity(name: str, q: Any) -> Quantity:
    path = f"quantities.{name}"
    q = _mapping(q, path)
    _check_keys(q, path, {"unit", "max_age_days", "min", "max", "conflict_tolerance"}, set())
    lo, hi = _num(q["min"], f"{path}.min"), _num(q["max"], f"{path}.max")
    if lo > hi:
        raise ConfigError(f"{path}: min ({lo}) is greater than max ({hi})")
    tol = _num(q["conflict_tolerance"], f"{path}.conflict_tolerance")
    if tol < 0:
        raise ConfigError(f"{path}.conflict_tolerance: must be >= 0")
    return Quantity(
        name=name,
        unit=_str(q["unit"], f"{path}.unit"),
        max_age_days=_pos_int(q["max_age_days"], f"{path}.max_age_days"),
        min=lo,
        max=hi,
        conflict_tolerance=tol,
    )


def _common(name: str, s: dict[str, Any], path: str) -> dict[str, Any]:
    return dict(
        name=name,
        adapter=s["adapter"],
        enabled=_bool(s.get("enabled", True), f"{path}.enabled"),
        on_failure=_choice(s.get("on_failure", "previous"), f"{path}.on_failure", ON_FAILURE),
        source_url=_str(s["source_url"], f"{path}.source_url"),
        tos_note=_str(s["tos_note"], f"{path}.tos_note"),
    )


def _quantity_ref(v: Any, path: str, quantities: dict[str, Quantity]) -> str:
    v = _str(v, path)
    if v not in quantities:
        raise ConfigError(f"{path}: unknown quantity {v!r}")
    return v


def _parse_evds(name, s, path, quantities) -> EvdsSource:
    _check_keys(s, path, _COMMON_REQUIRED | {"base_url", "series"},
                _COMMON_OPTIONAL | {"api_key_env", "lookback_days", "timeout_seconds"})
    if not isinstance(s["series"], list) or not s["series"]:
        raise ConfigError(f"{path}.series: must be a non-empty list")
    series, seen = [], set()
    for i, item in enumerate(s["series"]):
        p = f"{path}.series[{i}]"
        item = _mapping(item, p)
        _check_keys(item, p, {"code", "quantity", "verified"},
                    {"entity", "frequency", "lookback_days", "annual_change"})
        code = _str(item["code"], f"{p}.code")
        if code in seen:
            raise ConfigError(f"{p}.code: duplicate series code {code!r}")
        seen.add(code)
        verified = _bool(item["verified"], f"{p}.verified")
        if code.startswith(VERIFY_PREFIX) and verified:
            raise ConfigError(f"{p}: placeholder code {code!r} cannot be verified: true")
        frequency = _choice(item.get("frequency", "daily"), f"{p}.frequency", FREQUENCIES)
        lookback = item.get("lookback_days")
        series.append(EvdsSeries(
            code=code,
            quantity=_quantity_ref(item["quantity"], f"{p}.quantity", quantities),
            entity=_str(item.get("entity", code), f"{p}.entity"),
            frequency=frequency,
            verified=verified,
            lookback_days=None if lookback is None else _pos_int(lookback, f"{p}.lookback_days"),
            annual_change=(None if "annual_change" not in item else _parse_annual_change(
                item["annual_change"], f"{p}.annual_change", frequency, quantities)),
        ))
    timeout = _num(s.get("timeout_seconds", 20), f"{path}.timeout_seconds")
    if timeout <= 0:
        raise ConfigError(f"{path}.timeout_seconds: must be > 0")
    return EvdsSource(
        **_common(name, s, path),
        base_url=_str(s["base_url"], f"{path}.base_url"),
        api_key_env=_str(s.get("api_key_env", "EVDS_API_KEY"), f"{path}.api_key_env"),
        lookback_days=_pos_int(s.get("lookback_days", 120), f"{path}.lookback_days"),
        timeout_seconds=timeout,
        series=tuple(series),
    )


def _parse_annual_change(v: Any, path: str, frequency: str,
                         quantities: dict[str, Quantity]) -> AnnualChange:
    v = _mapping(v, path)
    _check_keys(v, path, {"quantity", "entity"}, set())
    if frequency != "monthly":
        # The change compares month M with month M - 12; other frequencies have
        # no single observation per month.
        raise ConfigError(f"{path}: needs frequency monthly, got {frequency!r}")
    return AnnualChange(quantity=_quantity_ref(v["quantity"], f"{path}.quantity", quantities),
                        entity=_str(v["entity"], f"{path}.entity"))


def _parse_tefas(name, s, path, quantities) -> TefasSource:
    _check_keys(s, path,
                _COMMON_REQUIRED | {"inbox", "date_column", "entity_column",
                                    "column_aliases", "value_columns"},
                _COMMON_OPTIONAL | {"file_patterns"})
    aliases: dict[str, tuple[str, ...]] = {}
    owner: dict[str, str] = {}
    for canon, names in _mapping(s["column_aliases"], f"{path}.column_aliases").items():
        p = f"{path}.column_aliases.{canon}"
        aliases[canon] = _str_list(names, p)
        for alias in aliases[canon]:
            key = normalize_header(alias)
            if key in owner and owner[key] != canon:
                raise ConfigError(f"{p}: alias {alias!r} is also used by {owner[key]!r}")
            owner[key] = canon

    date_col = _str(s["date_column"], f"{path}.date_column")
    entity_col = _str(s["entity_column"], f"{path}.entity_column")
    for col, key in ((date_col, "date_column"), (entity_col, "entity_column")):
        if col not in aliases:
            raise ConfigError(f"{path}.{key}: {col!r} has no entry in column_aliases")

    value_columns: dict[str, str] = {}
    for canon, qty in _mapping(s["value_columns"], f"{path}.value_columns").items():
        p = f"{path}.value_columns.{canon}"
        if canon not in aliases:
            raise ConfigError(f"{p}: {canon!r} has no entry in column_aliases")
        if canon in (date_col, entity_col):
            raise ConfigError(f"{p}: date/entity column cannot be a value column")
        value_columns[canon] = _quantity_ref(qty, p, quantities)
    if not value_columns:
        raise ConfigError(f"{path}.value_columns: at least one value column is required")

    return TefasSource(
        **_common(name, s, path),
        inbox=_str(s["inbox"], f"{path}.inbox"),
        file_patterns=_str_list(s.get("file_patterns", ["*.xlsx", "*.csv"]),
                                f"{path}.file_patterns"),
        date_column=date_col,
        entity_column=entity_col,
        column_aliases=aliases,
        value_columns=value_columns,
    )


def _tefas_url(v: Any, path: str) -> str:
    url = _str(v, path)
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != TEFAS_WEB_HOST:
        raise ConfigError(f"{path}: must be an https URL on {TEFAS_WEB_HOST}")
    if parts.path.startswith(TEFAS_DISALLOWED_PREFIXES):
        raise ConfigError(f"{path}: {parts.path!r} is disallowed by "
                          f"tefas.gov.tr/robots.txt ({', '.join(TEFAS_DISALLOWED_PREFIXES)})")
    return url


def _parse_tefas_web(name, s, path, quantities) -> TefasWebSource:
    _check_keys(s, path, _COMMON_REQUIRED | {"url", "user_agent", "value_fields"},
                _COMMON_OPTIONAL | {"timeout_seconds", "min_funds", "flag_needs_check"})
    url = _tefas_url(s["url"], f"{path}.url")
    fields: dict[str, str] = {}
    for field, qty in _mapping(s["value_fields"], f"{path}.value_fields").items():
        fields[_str(field, f"{path}.value_fields")] = _quantity_ref(
            qty, f"{path}.value_fields.{field}", quantities)
    if not fields:
        raise ConfigError(f"{path}.value_fields: at least one field is required")
    timeout = _num(s.get("timeout_seconds", 30), f"{path}.timeout_seconds")
    if timeout <= 0:
        raise ConfigError(f"{path}.timeout_seconds: must be > 0")
    return TefasWebSource(
        **_common(name, s, path),
        url=url,
        user_agent=_str(s["user_agent"], f"{path}.user_agent"),
        timeout_seconds=timeout,
        min_funds=_pos_int(s.get("min_funds", 1000), f"{path}.min_funds"),
        value_fields=fields,
        flag_needs_check=_bool(s.get("flag_needs_check", True), f"{path}.flag_needs_check"),
    )


def _detail_field(v: Any, path: str) -> str:
    field = _str(v, path)
    obj, _, key = field.partition(".")
    if obj not in DETAIL_OBJECTS or not key:
        raise ConfigError(f"{path}: {field!r} must be bilgiData.<field> or profilData.<field>")
    return field


def _detail_fields(v: Any, path: str, quantities: dict[str, Quantity]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for field, qty in _mapping(v, path).items():
        fields[_detail_field(field, path)] = _quantity_ref(qty, f"{path}.{field}", quantities)
    return fields


def _status_map(v: Any, path: str, quantities: dict[str, Quantity]) -> StatusMap:
    v = _mapping(v, path)
    _check_keys(v, path, {"field", "quantity", "map"}, set())
    texts = _mapping(v["map"], f"{path}.map")
    if not texts:
        raise ConfigError(f"{path}.map: must not be empty")
    out: dict[str, float] = {}
    for text, flag in texts.items():
        p = f"{path}.map.{text}"
        if _num(flag, p) not in (0, 1):
            raise ConfigError(f"{p}: must be 0 or 1")
        key = normalize_status(_str(text, p))
        if key in out:
            raise ConfigError(f"{p}: same text after normalization as another entry ({key!r})")
        out[key] = float(flag)
    return StatusMap(field=_detail_field(v["field"], f"{path}.field"),
                     quantity=_quantity_ref(v["quantity"], f"{path}.quantity", quantities),
                     map=out)


def _parse_tefas_detail(name, s, path, quantities) -> TefasDetailSource:
    _check_keys(s, path, _COMMON_REQUIRED | {"url", "user_agent", "value_fields"},
                _COMMON_OPTIONAL | {"timeout_seconds", "min_interval_s", "max_fail_share",
                                    "max_funds", "funds_from", "exclude_categories",
                                    "optional_fields", "flag_needs_check", "status",
                                    "holdings_quantity"})
    url = _tefas_url(s["url"], f"{path}.url")
    if "{code}" not in url:
        raise ConfigError(f"{path}.url: must contain {{code}} for the fund code")
    value_fields = _detail_fields(s["value_fields"], f"{path}.value_fields", quantities)
    if not value_fields:
        raise ConfigError(f"{path}.value_fields: at least one field is required")
    optional = _detail_fields(s.get("optional_fields", {}), f"{path}.optional_fields", quantities)
    both = sorted(value_fields.keys() & optional.keys())
    if both:
        raise ConfigError(f"{path}.optional_fields: {both} also in value_fields")
    timeout = _num(s.get("timeout_seconds", 30), f"{path}.timeout_seconds")
    if timeout <= 0:
        raise ConfigError(f"{path}.timeout_seconds: must be > 0")
    interval = _num(s.get("min_interval_s", 1.0), f"{path}.min_interval_s")
    if interval < 0:
        raise ConfigError(f"{path}.min_interval_s: must be >= 0")
    share = _num(s.get("max_fail_share", 0.05), f"{path}.max_fail_share")
    if not 0 <= share < 1:
        raise ConfigError(f"{path}.max_fail_share: must be between 0 and 1 (1 not included)")
    max_funds = s.get("max_funds")
    excluded = s.get("exclude_categories", [])
    if not isinstance(excluded, list):
        raise ConfigError(f"{path}.exclude_categories: must be a list")
    return TefasDetailSource(
        **_common(name, s, path),
        url=url,
        user_agent=_str(s["user_agent"], f"{path}.user_agent"),
        timeout_seconds=timeout,
        min_interval_s=interval,
        max_fail_share=share,
        max_funds=None if max_funds is None else _pos_int(max_funds, f"{path}.max_funds"),
        funds_from=_funds_from(s.get("funds_from", "tefas_web"), f"{path}.funds_from"),
        exclude_categories=tuple(_str(x, f"{path}.exclude_categories[{i}]")
                                 for i, x in enumerate(excluded)),
        value_fields=value_fields,
        optional_fields=optional,
        flag_needs_check=_bool(s.get("flag_needs_check", True), f"{path}.flag_needs_check"),
        status=_status_map(s["status"], f"{path}.status", quantities) if "status" in s else None,
        holdings_quantity=(_quantity_ref(s["holdings_quantity"], f"{path}.holdings_quantity",
                                         quantities) if "holdings_quantity" in s else None),
    )


def _funds_from(v: Any, path: str) -> tuple[str, ...]:
    """One source name, or a list of them (I10: tefas_web and tefas_byf)."""
    if not isinstance(v, list):
        return (_str(v, path),)
    names = _str_list(v, path)
    for i, name in enumerate(names):
        if name in names[:i]:
            raise ConfigError(f"{path}[{i}]: {name!r} is listed twice")
    return names


def _parse_manual(name, s, path, quantities) -> ManualSource:
    _check_keys(s, path, _COMMON_REQUIRED | {"inbox", "allowed_quantities"},
                _COMMON_OPTIONAL | {"file_patterns"})
    allowed = _str_list(s["allowed_quantities"], f"{path}.allowed_quantities")
    for i, q in enumerate(allowed):
        _quantity_ref(q, f"{path}.allowed_quantities[{i}]", quantities)
    return ManualSource(
        **_common(name, s, path),
        inbox=_str(s["inbox"], f"{path}.inbox"),
        file_patterns=_str_list(s.get("file_patterns", ["*.csv"]), f"{path}.file_patterns"),
        allowed_quantities=allowed,
    )


def _parse_bist_bulletin(name, s, path, quantities) -> BistBulletinSource:
    _check_keys(s, path, _COMMON_REQUIRED | {"url", "user_agent"},
                _COMMON_OPTIONAL | {"timeout_seconds", "history_days", "min_interval_s",
                                    "recheck_days", "min_shares", "adjust_jump_pct",
                                    "price_limit_pct"})
    url = _str(s["url"], f"{path}.url")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != BIST_HOST:
        raise ConfigError(f"{path}.url: must be an https URL on {BIST_HOST}")
    if not parts.path.startswith("/data/"):
        raise ConfigError(f"{path}.url: must be under /data/ (the bulletin files)")
    if "{yyyymmdd}" not in url:
        raise ConfigError(f"{path}.url: must contain {{yyyymmdd}} for the bulletin date")
    try:
        url.format(yyyy="2026", mm="01", yyyymmdd="20260101")
    except (KeyError, IndexError, ValueError) as e:
        raise ConfigError(f"{path}.url: unknown field {e} (allowed: {{yyyy}}, {{mm}}, "
                          f"{{yyyymmdd}})") from None
    for q in BIST_QUANTITIES:
        if q not in quantities:
            raise ConfigError(f"{path}: quantity {q!r} is not in quantities")
    timeout = _num(s.get("timeout_seconds", 30), f"{path}.timeout_seconds")
    if timeout <= 0:
        raise ConfigError(f"{path}.timeout_seconds: must be > 0")
    interval = _num(s.get("min_interval_s", 1.0), f"{path}.min_interval_s")
    if interval < 0:
        raise ConfigError(f"{path}.min_interval_s: must be >= 0")
    recheck = s.get("recheck_days", 3)
    if isinstance(recheck, bool) or not isinstance(recheck, int) or recheck < 0:
        raise ConfigError(f"{path}.recheck_days: must be >= 0 (an integer)")
    jump = _num(s.get("adjust_jump_pct", 10.5), f"{path}.adjust_jump_pct")
    if not 0 < jump < 100:
        raise ConfigError(f"{path}.adjust_jump_pct: must be between 0 and 100 (both excluded)")
    price_limit = _num(s.get("price_limit_pct", 10.0), f"{path}.price_limit_pct")
    if not 0 < price_limit < 100:
        raise ConfigError(f"{path}.price_limit_pct: must be between 0 and 100 (both excluded)")
    return BistBulletinSource(
        **_common(name, s, path),
        url=url,
        user_agent=_str(s["user_agent"], f"{path}.user_agent"),
        timeout_seconds=timeout,
        history_days=_pos_int(s.get("history_days", 400), f"{path}.history_days"),
        min_interval_s=interval,
        recheck_days=recheck,
        min_shares=_pos_int(s.get("min_shares", 100), f"{path}.min_shares"),
        adjust_jump_pct=jump,
        price_limit_pct=price_limit,
    )


_ING_FORM_KEYS = {"currency_field", "product_field", "send_target", "currency", "no_product"}
_ING_PRODUCT_KEYS = {"value", "layout", "entity", "min_rows", "min_columns"}
_ING_BALANCE_KEYS = {"balance_header", "rates"}
_ING_ENTITY_FIELDS = {"grid": {"row", "column"}, "balance": {"rate", "balance"}}


def _str_map(v: Any, path: str, *, non_empty: bool) -> dict[str, str]:
    m = _mapping(v, path)
    if non_empty and not m:
        raise ConfigError(f"{path}: must not be empty")
    return {_str(k, f"{path} key"): _str(x, f"{path}.{k}") for k, x in m.items()}


def _parse_ing_product(item: Any, p: str) -> IngProduct:
    item = _mapping(item, p)
    layout = _choice(item.get("layout"), f"{p}.layout", ING_LAYOUTS)
    if layout == "grid":
        _check_keys(item, p, _ING_PRODUCT_KEYS, set())
    else:
        _check_keys(item, p, _ING_PRODUCT_KEYS | _ING_BALANCE_KEYS,
                    {"balance_labels", "no_interest_column"})
    entity = _str(item["entity"], f"{p}.entity")
    try:
        fields = {f for _, f, _, _ in string.Formatter().parse(entity) if f is not None}
    except ValueError as e:
        raise ConfigError(f"{p}.entity: {e}") from None
    if fields != _ING_ENTITY_FIELDS[layout]:
        raise ConfigError(f"{p}.entity: must use exactly the fields "
                          f"{sorted(_ING_ENTITY_FIELDS[layout])}, got {sorted(fields)}")
    extra: dict[str, Any] = {}
    if layout == "balance":
        extra = dict(
            balance_header=_str(item["balance_header"], f"{p}.balance_header"),
            no_interest_column=(_str(item["no_interest_column"], f"{p}.no_interest_column")
                                if "no_interest_column" in item else ""),
            rates=_str_map(item["rates"], f"{p}.rates", non_empty=True),
            balance_labels=_str_map(item.get("balance_labels", {}), f"{p}.balance_labels",
                                    non_empty=False))
    return IngProduct(value=_str(item["value"], f"{p}.value"), layout=layout, entity=entity,
                      min_rows=_pos_int(item["min_rows"], f"{p}.min_rows"),
                      min_columns=_pos_int(item["min_columns"], f"{p}.min_columns"), **extra)


def _parse_ing_web(name, s, path, quantities) -> IngWebSource:
    """I14: ING's own rate page, an ASP.NET form (3 requests per product)."""
    _check_keys(s, path, _COMMON_REQUIRED | {"url", "user_agent", "quantity", "form", "products"},
                _COMMON_OPTIONAL | {"timeout_seconds", "delay_seconds"})
    url = _str(s["url"], f"{path}.url")
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != ING_HOST:
        raise ConfigError(f"{path}.url: must be an https URL on {ING_HOST}")
    if ing_robots_disallows(url):
        raise ConfigError(f"{path}.url: {parts.path!r} is disallowed by ing.com.tr/robots.txt")
    form = _mapping(s["form"], f"{path}.form")
    _check_keys(form, f"{path}.form", _ING_FORM_KEYS, set())
    if not isinstance(s["products"], list) or not s["products"]:
        raise ConfigError(f"{path}.products: must be a non-empty list")
    products: list[IngProduct] = []
    for i, item in enumerate(s["products"]):
        product = _parse_ing_product(item, f"{path}.products[{i}]")
        if any(product.value == other.value for other in products):
            raise ConfigError(f"{path}.products[{i}].value: {product.value!r} is listed twice")
        products.append(product)
    timeout = _num(s.get("timeout_seconds", 30), f"{path}.timeout_seconds")
    if timeout <= 0:
        raise ConfigError(f"{path}.timeout_seconds: must be > 0")
    delay = _num(s.get("delay_seconds", 2), f"{path}.delay_seconds")
    if delay < 0:
        raise ConfigError(f"{path}.delay_seconds: must be >= 0")
    return IngWebSource(
        **_common(name, s, path),
        url=url,
        user_agent=_str(s["user_agent"], f"{path}.user_agent"),
        timeout_seconds=timeout,
        delay_seconds=delay,
        quantity=_quantity_ref(s["quantity"], f"{path}.quantity", quantities),
        form=IngForm(**{k: _str(form[k], f"{path}.form.{k}") for k in sorted(_ING_FORM_KEYS)}),
        products=tuple(products),
    )


def _parse_bank_table(name, s, path, quantities) -> BankTableSource:
    """I15: rate tables on a bank's own page (one GET)."""
    _check_keys(s, path, _COMMON_REQUIRED | {"url", "user_agent", "quantity", "tables"},
                _COMMON_OPTIONAL | {"timeout_seconds"})
    url = _str(s["url"], f"{path}.url")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise ConfigError(f"{path}.url: must be an https URL")
    if parts.netloc not in BANK_ROBOTS_DISALLOW:
        raise ConfigError(f"{path}.url: no robots.txt rules in the code for {parts.netloc!r}")
    if robots_disallows(BANK_ROBOTS_DISALLOW[parts.netloc], url):
        raise ConfigError(f"{path}.url: {parts.path!r} is disallowed by "
                          f"{parts.netloc}/robots.txt")
    if not isinstance(s["tables"], list) or not s["tables"]:
        raise ConfigError(f"{path}.tables: must be a non-empty list")
    tables: list[BankTable] = []
    for i, item in enumerate(s["tables"]):
        p = f"{path}.tables[{i}]"
        item = _mapping(item, p)
        _check_keys(item, p, {"header", "entity", "decimal", "min_rows"}, {"skip_rows", "note"})
        header = item["header"]
        if not isinstance(header, list) or len(header) < 2:
            raise ConfigError(f"{p}.header: needs the row label cell and at least one column")
        header = tuple(" ".join(_str(h, f"{p}.header[{k}]").split()) for k, h in enumerate(header))
        for j, other in enumerate(tables):
            if other.header == header:
                raise ConfigError(f"{p}.header: the same header as tables[{j}]")
        entity = _str(item["entity"], f"{p}.entity")
        fields = {f for _, f, _, _ in string.Formatter().parse(entity) if f is not None}
        if fields != {"row", "column"}:
            raise ConfigError(f"{p}.entity: must use exactly the fields ['column', 'row'], "
                              f"got {sorted(fields)}")
        skip = item.get("skip_rows", [])
        if not isinstance(skip, list):
            raise ConfigError(f"{p}.skip_rows: must be a list of strings")
        tables.append(BankTable(
            header=header, entity=entity,
            decimal=_choice(item["decimal"], f"{p}.decimal", (",", ".")),
            min_rows=_pos_int(item["min_rows"], f"{p}.min_rows"),
            skip_rows=tuple(" ".join(_str(r, f"{p}.skip_rows[{k}]").split())
                            for k, r in enumerate(skip)),
            note=_str(item["note"], f"{p}.note") if "note" in item else ""))
    timeout = _num(s.get("timeout_seconds", 30), f"{path}.timeout_seconds")
    if timeout <= 0:
        raise ConfigError(f"{path}.timeout_seconds: must be > 0")
    return BankTableSource(
        **_common(name, s, path), url=url,
        user_agent=_str(s["user_agent"], f"{path}.user_agent"), timeout_seconds=timeout,
        quantity=_quantity_ref(s["quantity"], f"{path}.quantity", quantities),
        tables=tuple(tables))


_PARSERS = {"evds": _parse_evds, "tefas": _parse_tefas, "tefas_web": _parse_tefas_web,
            "tefas_detail": _parse_tefas_detail, "manual": _parse_manual,
            "bist_bulletin": _parse_bist_bulletin, "ing_web": _parse_ing_web,
            "bank_table": _parse_bank_table}
