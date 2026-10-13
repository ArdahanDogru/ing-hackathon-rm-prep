"""Load and validate config/sources.yaml.

`load_raw` reads the YAML; `parse_config` validates a plain dict. The raw dict
is what goes into the snapshot manifest, so replay calls `parse_config` on the
manifest copy and never re-reads the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import yaml

CONFIG_VERSION = 1
ADAPTERS = ("evds", "tefas", "tefas_web", "tefas_detail", "manual")
TEFAS_WEB_HOST = "www.tefas.gov.tr"
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
    funds_from: str                  # tefas_web source that gives the fund list
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
        if isinstance(src, TefasDetailSource) and not isinstance(
                sources.get(src.funds_from), TefasWebSource):
            raise ConfigError(f"sources.{name}.funds_from: must name a tefas_web source, "
                              f"got {src.funds_from!r}")
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
        funds_from=_str(s.get("funds_from", "tefas_web"), f"{path}.funds_from"),
        exclude_categories=tuple(_str(x, f"{path}.exclude_categories[{i}]")
                                 for i, x in enumerate(excluded)),
        value_fields=value_fields,
        optional_fields=optional,
        flag_needs_check=_bool(s.get("flag_needs_check", True), f"{path}.flag_needs_check"),
        status=_status_map(s["status"], f"{path}.status", quantities) if "status" in s else None,
        holdings_quantity=(_quantity_ref(s["holdings_quantity"], f"{path}.holdings_quantity",
                                         quantities) if "holdings_quantity" in s else None),
    )


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


_PARSERS = {"evds": _parse_evds, "tefas": _parse_tefas, "tefas_web": _parse_tefas_web,
            "tefas_detail": _parse_tefas_detail, "manual": _parse_manual}
