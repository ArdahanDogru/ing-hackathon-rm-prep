"""Fund documents (I16): links to the official izahname and yatırımcı bilgi formu
(YBF) of a fund on its manager's own site.

LINKS ONLY: only HTML pages are requested (a fund page, a list page); no PDF is
requested, downloaded, stored or read (no HEAD either). Not from KAP (it
blocks bots) and not from mirror sites. On demand: the API calls
`find_documents` when the RM opens a fund drawer; it is not in the daily
ingest and not in a snapshot.

Per manager (config/fund_docs.yaml): the issuer texts that map to it, the site,
the verdict (`ok`; `link_only` = the terms forbid copying: only the URL and the
label are kept, no page is stored), the robots Disallow lines (checked before
each request and for each document link), the way to the fund page (a URL
template, list pages to look the code up in, or fixed pages that list all
funds), the link rules per kind and the date patterns.

Requests: at most `max_requests` per call (redirects count), `delay_seconds`
between two requests to one host (a lock per host for the whole process: the
API serves several RMs), no redirect to another host, honest User-Agent.
Cache (Turkish day): the result `<CODE>-<YYYY-MM-DD>.json` (`ok` and
`not_found`; `failed` is not cached) and, for `ok` managers only, the list and
shared pages, so a second fund of the same list costs no request.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import httpx
import yaml

from rmprep.contracts import TR_TZ
from rmprep.ingest.config import (
    ConfigError,
    _check_keys,
    _choice,
    _mapping,
    _num,
    _pos_int,
    _str,
    _str_list,
    robots_disallows,
)

KINDS = ("izahname", "ybf")
VERDICTS = ("ok", "link_only")
PICKS = ("newest", "first")       # newest by date, else first | first on the page
CONFIG_VERSION = 1
NO_RULE = {"tr": "Bu kurucunun sitesi için kural yok.",
           "en": "There is no rule for this fund manager's site."}
NOT_IN_LIST = {"tr": "Fon sayfası kurucunun listesinde bulunamadı.",
               "en": "The fund page is not in the manager's list."}
NO_LINK = {"tr": "Kurucunun sayfasında belge bağlantısı bulunamadı.",
           "en": "The manager's page has no document link."}
_REDIRECTS = (301, 302, 303, 307, 308)
_SAFE = "/%:@!$&'()*+,;=-._~"


# --- results ----------------------------------------------------------------------------------

@dataclass(frozen=True)
class FundDoc:
    kind: str                        # "izahname" | "ybf"
    url: str                         # absolute, percent-encoded
    label: str                       # the link text as on the page
    date: date | None

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "url": self.url, "label": self.label,
                "date": self.date.isoformat() if self.date else None}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> FundDoc:
        return cls(kind=d["kind"], url=d["url"], label=d["label"],
                   date=date.fromisoformat(d["date"]) if d["date"] else None)


@dataclass(frozen=True)
class FundDocs:
    code: str
    manager: str                     # the manager key; "" when not covered
    manager_label: str
    verdict: str                     # "ok" | "link_only" | ""
    status: str                      # "ok" | "not_found" | "not_covered" | "failed"
    docs: tuple[FundDoc, ...]
    page_url: str
    page_sha256: str
    checked_at: datetime | None
    reason: dict[str, str] | None    # {"tr": ..., "en": ...}

    def to_json(self) -> dict[str, Any]:
        return {"code": self.code, "manager": self.manager, "manager_label": self.manager_label,
                "verdict": self.verdict, "status": self.status,
                "docs": [d.to_json() for d in self.docs], "page_url": self.page_url,
                "page_sha256": self.page_sha256,
                "checked_at": self.checked_at.isoformat() if self.checked_at else None,
                "reason": self.reason}

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> FundDocs:
        return cls(code=d["code"], manager=d["manager"], manager_label=d["manager_label"],
                   verdict=d["verdict"], status=d["status"],
                   docs=tuple(FundDoc.from_json(x) for x in d["docs"]), page_url=d["page_url"],
                   page_sha256=d["page_sha256"],
                   checked_at=(datetime.fromisoformat(d["checked_at"]).astimezone(TR_TZ)
                               if d["checked_at"] else None),
                   reason=d["reason"])


# --- config -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Lookup:
    """A list page where the code leads to the fund page: an <a> whose path
    matches `href` and whose text matches `text`, or `raw` with a group `url`
    on the page source."""
    url: str
    href: str | None = None
    text: str | None = None
    raw: str | None = None


@dataclass(frozen=True)
class DocRule:
    kind: str
    page: int | None = None          # index into `pages` (fixed pages only)
    label: str | None = None
    before: str | None = None
    path: str | None = None
    exclude: str | None = None


@dataclass(frozen=True)
class Manager:
    key: str
    label: str
    issuers: tuple[str, ...]
    site: str
    site_host: str
    doc_hosts: tuple[str, ...]
    verdict: str
    robots_disallow: tuple[str, ...]
    template: str | None
    lookups: tuple[Lookup, ...]
    pages: tuple[str, ...]
    docs: tuple[DocRule, ...]
    dates: tuple[str, ...]
    pick: str = "newest"

    @property
    def hosts(self) -> set[str]:
        return {self.site_host, *self.doc_hosts}


@dataclass(frozen=True)
class NotCovered:
    issuers: tuple[str, ...]
    reason: dict[str, str]


@dataclass(frozen=True)
class FundDocsConfig:
    user_agent: str
    timeout_seconds: float
    delay_seconds: float
    max_requests: int
    managers: tuple[Manager, ...]
    not_covered: tuple[NotCovered, ...]

    def manager(self, key: str) -> Manager:
        return next(m for m in self.managers if m.key == key)


def load_config(path: str | Path) -> FundDocsConfig:
    with open(path, encoding="utf-8") as f:
        return parse_config(yaml.safe_load(f))


def tr_lower(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower()


def _fill(pattern: str, code: str, escape: bool = True) -> str:
    """The code placeholders of a regex (escaped) or a URL (as is)."""
    f = re.escape if escape else (lambda s: s)
    return (pattern.replace("{code_tr_lower}", f(tr_lower(code)))
            .replace("{code_lower}", f(code.lower())).replace("{code}", f(code)))


def _regex(v: Any, path: str) -> str:
    v = _str(v, path)
    try:
        re.compile(_fill(v, "ABC"))
    except re.error as e:
        raise ConfigError(f"{path}: bad regex ({e})") from None
    return v


def _https(v: Any, path: str) -> str:
    v = _str(v, path)
    parts = urlsplit(v)
    if parts.scheme != "https" or not parts.netloc:
        raise ConfigError(f"{path}: must be an https URL")
    return v


def _norm_issuer(text: str) -> str:
    return " ".join(text.split()).casefold()


def _parse_manager(m: Any, p: str) -> Manager:
    m = _mapping(m, p)
    _check_keys(m, p, {"key", "label", "issuers", "site", "verdict", "fund_page", "docs"},
                {"doc_hosts", "robots_disallow", "dates", "pick"})
    site = _https(m["site"], f"{p}.site").rstrip("/")
    fp = _mapping(m["fund_page"], f"{p}.fund_page")
    ways = [k for k in ("template", "lookups", "pages") if k in fp]
    if len(ways) != 1 or set(fp) - {"template", "lookups", "pages"}:
        raise ConfigError(f"{p}.fund_page: exactly one of template, lookups, pages")
    template, lookups, pages = None, (), ()
    if "template" in fp:
        template = _https(fp["template"], f"{p}.fund_page.template")
    elif "lookups" in fp:
        if not isinstance(fp["lookups"], list) or not fp["lookups"]:
            raise ConfigError(f"{p}.fund_page.lookups: must be a non-empty list")
        items = []
        for i, lk in enumerate(fp["lookups"]):
            q = f"{p}.fund_page.lookups[{i}]"
            lk = _mapping(lk, q)
            _check_keys(lk, q, {"url"}, {"href", "text", "raw"})
            if not set(lk) & {"href", "text", "raw"}:
                raise ConfigError(f"{q}: needs at least one of href, text, raw")
            raw = _regex(lk["raw"], f"{q}.raw") if "raw" in lk else None
            if raw is not None and "url" not in re.compile(_fill(raw, "ABC")).groupindex:
                raise ConfigError(f"{q}.raw: needs the group url")
            items.append(Lookup(url=_https(lk["url"], f"{q}.url"),
                                href=_regex(lk["href"], f"{q}.href") if "href" in lk else None,
                                text=_regex(lk["text"], f"{q}.text") if "text" in lk else None,
                                raw=raw))
        lookups = tuple(items)
    else:
        pages = tuple(_https(u, f"{p}.fund_page.pages[{i}]")
                      for i, u in enumerate(_str_list(fp["pages"], f"{p}.fund_page.pages")))
    if not isinstance(m["docs"], list) or not m["docs"]:
        raise ConfigError(f"{p}.docs: must be a non-empty list")
    rules = []
    for i, r in enumerate(m["docs"]):
        q = f"{p}.docs[{i}]"
        r = _mapping(r, q)
        _check_keys(r, q, {"kind"}, {"page", "label", "before", "path", "exclude"})
        if not set(r) & {"label", "before", "path"}:
            raise ConfigError(f"{q}: needs at least one of label, before, path")
        page = r.get("page")
        if page is not None and (isinstance(page, bool) or not isinstance(page, int)
                                 or not 0 <= page < len(pages)):
            raise ConfigError(f"{q}.page: must be the index of one of the {len(pages)} pages")
        rules.append(DocRule(kind=_choice(r["kind"], f"{q}.kind", KINDS), page=page,
                             **{k: _regex(r[k], f"{q}.{k}") if k in r else None
                                for k in ("label", "before", "path", "exclude")}))
    dates = []
    for i, d in enumerate(m.get("dates", [])):
        rx = _regex(d, f"{p}.dates[{i}]")
        if not {"d", "m", "y"} <= set(re.compile(rx).groupindex):
            raise ConfigError(f"{p}.dates[{i}]: needs the groups d, m, y")
        dates.append(rx)
    disallow = m.get("robots_disallow", [])
    if not isinstance(disallow, list):
        raise ConfigError(f"{p}.robots_disallow: must be a list")
    hosts = m.get("doc_hosts", [])
    if not isinstance(hosts, list):
        raise ConfigError(f"{p}.doc_hosts: must be a list")
    return Manager(
        key=_str(m["key"], f"{p}.key"), label=_str(m["label"], f"{p}.label"),
        issuers=_str_list(m["issuers"], f"{p}.issuers"), site=site,
        site_host=urlsplit(site).netloc,
        doc_hosts=tuple(_str(h, f"{p}.doc_hosts[{i}]") for i, h in enumerate(hosts)),
        verdict=_choice(m["verdict"], f"{p}.verdict", VERDICTS),
        robots_disallow=tuple(_str(x, f"{p}.robots_disallow[{i}]") for i, x in enumerate(disallow)),
        template=template, lookups=lookups, pages=pages, docs=tuple(rules), dates=tuple(dates),
        pick=_choice(m.get("pick", "newest"), f"{p}.pick", PICKS))


def parse_config(raw: Any) -> FundDocsConfig:
    raw = _mapping(raw, "fund_docs")
    _check_keys(raw, "fund_docs", {"version", "user_agent", "managers"},
                {"timeout_seconds", "delay_seconds", "max_requests", "not_covered"})
    if raw["version"] != CONFIG_VERSION:
        raise ConfigError(f"version: expected {CONFIG_VERSION}, got {raw['version']!r}")
    if not isinstance(raw["managers"], list) or not raw["managers"]:
        raise ConfigError("managers: must be a non-empty list")
    managers = tuple(_parse_manager(m, f"managers[{i}]") for i, m in enumerate(raw["managers"]))
    not_covered = []
    for i, nc in enumerate(raw.get("not_covered", [])):
        q = f"not_covered[{i}]"
        nc = _mapping(nc, q)
        _check_keys(nc, q, {"issuers", "reason"}, set())
        reason = _mapping(nc["reason"], f"{q}.reason")
        _check_keys(reason, f"{q}.reason", {"tr", "en"}, set())
        not_covered.append(NotCovered(issuers=_str_list(nc["issuers"], f"{q}.issuers"),
                                      reason={k: _str(reason[k], f"{q}.reason.{k}")
                                              for k in ("tr", "en")}))
    seen: set[str] = set()
    for owner in [*managers, *not_covered]:
        for issuer in owner.issuers:
            if _norm_issuer(issuer) in seen:
                raise ConfigError(f"issuer {issuer!r} is listed twice")
            seen.add(_norm_issuer(issuer))
    keys = [m.key for m in managers]
    if len(keys) != len(set(keys)):
        raise ConfigError("managers: a key is listed twice")
    delay = _num(raw.get("delay_seconds", 2), "delay_seconds")
    timeout = _num(raw.get("timeout_seconds", 20), "timeout_seconds")
    if delay < 0 or timeout <= 0:
        raise ConfigError("delay_seconds must be >= 0 and timeout_seconds > 0")
    return FundDocsConfig(user_agent=_str(raw["user_agent"], "user_agent"),
                          timeout_seconds=timeout, delay_seconds=delay,
                          max_requests=_pos_int(raw.get("max_requests", 3), "max_requests"),
                          managers=managers, not_covered=tuple(not_covered))


# --- links on a page ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Link:
    url: str                         # absolute (not yet percent-encoded)
    label: str                       # the text of the <a>
    before: str                      # the last text before the <a> (TEB: the item title)


class _Links(HTMLParser):
    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base, self.links = base, []
        self._open: list[str] | None = None
        self._href = ""
        self._last = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = (dict(attrs).get("href") or "").strip()
            self._open, self._before = [], self._last

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._open is not None:
            if self._href and not self._href.startswith(("#", "javascript:", "mailto:", "tel:")):
                self.links.append(Link(url=urljoin(self.base, self._href),
                                       label=" ".join(" ".join(self._open).split()),
                                       before=self._before[-300:]))
            self._open = None

    def handle_data(self, data: str) -> None:
        if self._open is not None:
            self._open.append(data)
        elif data.strip():
            self._last = " ".join(data.split())


def read_links(html: str, base_url: str) -> list[Link]:
    parser = _Links(base_url)
    parser.feed(html)
    parser.close()
    return parser.links


def _path(url: str) -> str:
    return unquote(urlsplit(url).path)


def _encode(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, quote(p.path, safe=_SAFE),
                       quote(p.query, safe=_SAFE + "?"), ""))


def _usable(manager: Manager, url: str) -> bool:
    """An http(s) link on the manager's site or its document hosts, and not on
    a path its robots.txt disallows."""
    p = urlsplit(url)
    if p.scheme not in ("http", "https") or p.netloc not in manager.hosts:
        return False
    return not (p.netloc == manager.site_host and robots_disallows(manager.robots_disallow, url))


def date_of(manager: Manager, text: str) -> date | None:
    for rx in manager.dates:
        for m in re.finditer(rx, text):
            try:
                return date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
            except ValueError:
                continue
    return None


def _matches(rule: DocRule, code: str, link: Link) -> bool:
    path = _path(link.url)
    for field_, text in (("label", link.label), ("before", link.before), ("path", path)):
        rx = getattr(rule, field_)
        if rx is not None and not re.search(_fill(rx, code), text):
            return False
    if rule.exclude and re.search(_fill(rule.exclude, code), f"{link.label}\n{link.before}\n{path}"):
        return False
    return True


def select_docs(manager: Manager, code: str, pages: list[list[Link]]) -> tuple[FundDoc, ...]:
    """At most one link per kind: the newest by date, else the first on the page
    (`pick: first`: always the first on the page)."""
    out = []
    for kind in KINDS:
        found: list[Link] = []
        for rule in (r for r in manager.docs if r.kind == kind):
            links = pages[rule.page] if rule.page is not None else [x for p in pages for x in p]
            found += [x for x in links if _matches(rule, code, x) and _usable(manager, x.url)
                      and x.url not in {f.url for f in found}]
        if not found:
            continue
        dated = [(date_of(manager, f"{x.label} {_path(x.url)}"), i, x) for i, x in enumerate(found)]
        with_date = [t for t in dated if t[0] is not None]
        if manager.pick == "newest" and with_date:
            when, _, best = max(with_date, key=lambda t: (t[0], -t[1]))
        else:
            when, _, best = dated[0]
        out.append(FundDoc(kind=kind, url=_encode(best.url), label=best.label, date=when))
    return tuple(out)


# --- requests ----------------------------------------------------------------------------------

class _Fail(Exception):
    """A request or a page fails; the message is the reason."""


@dataclass
class _Host:
    lock: threading.Lock
    last: float | None = None


_HOSTS: dict[str, _Host] = {}
_HOSTS_LOCK = threading.Lock()


def reset_hosts() -> None:
    """Forget the time of the last request per host (tests)."""
    with _HOSTS_LOCK:
        _HOSTS.clear()


def _host(name: str) -> _Host:
    with _HOSTS_LOCK:
        return _HOSTS.setdefault(name, _Host(threading.Lock()))


class _Fetcher:
    def __init__(self, cfg: FundDocsConfig, manager: Manager, client: httpx.Client,
                 sleep: Callable[[float], None], monotonic: Callable[[], float]) -> None:
        self.cfg, self.manager, self.client = cfg, manager, client
        self.sleep, self.monotonic = sleep, monotonic
        self.count = 0

    def get(self, url: str) -> tuple[str, bytes]:
        """(final URL, body) of an HTML page of the manager's site."""
        for _ in range(self.cfg.max_requests + 1):
            parts = urlsplit(url)
            if parts.netloc != self.manager.site_host:
                raise _Fail(f"{url} is not on the manager's site")
            if parts.path.lower().endswith(".pdf"):
                raise _Fail("a PDF is never requested")
            if robots_disallows(self.manager.robots_disallow, url):
                raise _Fail(f"{parts.path} is disallowed by robots.txt")
            if self.count >= self.cfg.max_requests:
                n = self.cfg.max_requests
                raise _Fail(f"more than {n} request{'s' if n != 1 else ''} needed")
            self.count += 1
            resp = self._request(_encode(url))
            location = resp.headers.get("location")
            if resp.status_code in _REDIRECTS and location:
                url = urljoin(url, location)
                if urlsplit(url).netloc != self.manager.site_host:
                    raise _Fail("redirect to another host")
                continue
            if resp.status_code != 200:
                raise _Fail(f"HTTP {resp.status_code}")
            if "html" not in resp.headers.get("content-type", "").lower():
                raise _Fail("not an HTML page")
            return url, resp.content
        raise _Fail("too many redirects")

    def _request(self, url: str) -> httpx.Response:
        host = _host(urlsplit(url).netloc)
        with host.lock:
            if host.last is not None:
                wait = host.last + self.cfg.delay_seconds - self.monotonic()
                if wait > 0:
                    self.sleep(wait)
            try:
                return self.client.get(url, headers={"User-Agent": self.cfg.user_agent},
                                       timeout=self.cfg.timeout_seconds, follow_redirects=False)
            finally:
                host.last = self.monotonic()


# --- cache -------------------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _result_file(cache_dir: Path, code: str, day: date) -> Path | None:
    return cache_dir / f"{code}-{day.isoformat()}.json" if re.fullmatch(r"[A-Z0-9]{1,12}", code) else None


class _Pages:
    """Pages of one call; list and shared pages of `ok` managers are cached per
    day on disk (never the pages of `link_only` managers)."""

    def __init__(self, fetcher: _Fetcher, cache_dir: Path, day: date) -> None:
        self.fetcher, self.cache_dir, self.day = fetcher, cache_dir, day

    def get(self, url: str, shared: bool) -> tuple[str, bytes]:
        keep = shared and self.fetcher.manager.verdict == "ok"
        name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        path = self.cache_dir / "pages" / f"{self.fetcher.manager.key}-{name}-{self.day}.json"
        if keep and path.is_file():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                return d["url"], d["html"].encode("utf-8")
            except (ValueError, KeyError):
                pass
        final, body = self.fetcher.get(url)
        if keep:
            _write(path, json.dumps({"url": final, "html": body.decode("utf-8", "replace")},
                                    ensure_ascii=False))
        return final, body


# --- the call ----------------------------------------------------------------------------------

def _owner(cfg: FundDocsConfig, issuer: str) -> Manager | NotCovered | None:
    key = _norm_issuer(issuer)
    for owner in [*cfg.managers, *cfg.not_covered]:
        if key and key in {_norm_issuer(i) for i in owner.issuers}:
            return owner
    return None


def _text(body: bytes) -> str:
    return body.decode("utf-8", "replace")


def _find_fund_page(manager: Manager, code: str, pages: _Pages) -> tuple[str | None, str, bytes]:
    """(fund page URL or None, first list page URL, its body)."""
    first_url, first_body = "", b""
    for lk in manager.lookups:
        final, body = pages.get(lk.url, shared=True)
        if not first_url:
            first_url, first_body = final, body
        html = _text(body)
        if lk.raw:
            m = re.search(_fill(lk.raw, code), html)
            if m:
                return urljoin(manager.site + "/", m.group("url")), first_url, first_body
            continue
        for link in read_links(html, final):
            if urlsplit(link.url).netloc != manager.site_host:
                continue
            if lk.href and not re.search(_fill(lk.href, code), _path(link.url)):
                continue
            if lk.text and not re.search(_fill(lk.text, code), link.label):
                continue
            p = urlsplit(link.url)
            return urlunsplit((p.scheme, p.netloc, p.path, "", "")), first_url, first_body
    return None, first_url, first_body


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def find_documents(
    code: str,
    issuer: str,
    cfg: FundDocsConfig,
    *,
    client: httpx.Client,
    now: Callable[[], datetime] = lambda: datetime.now(TR_TZ),
    sleep: Callable[[float], None] = time.sleep,
    cache_dir: str | Path,
    monotonic: Callable[[], float] = time.monotonic,
) -> FundDocs:
    """The izahname and YBF links of one fund. Never raises: a site problem is
    status `failed` with a reason."""
    code = code.strip().upper()
    owner = _owner(cfg, issuer)

    def result(status: str, *, docs=(), page_url="", sha="", reason=None,
               manager: Manager | None = None) -> FundDocs:
        return FundDocs(code=code, manager=manager.key if manager else "",
                        manager_label=manager.label if manager else " ".join(issuer.split()),
                        verdict=manager.verdict if manager else "", status=status,
                        docs=tuple(docs), page_url=page_url, page_sha256=sha,
                        checked_at=now().astimezone(TR_TZ), reason=reason)

    if not isinstance(owner, Manager):
        return result("not_covered", reason=dict(owner.reason) if owner else dict(NO_RULE))
    manager = owner
    cache_dir = Path(cache_dir)
    day = now().astimezone(TR_TZ).date()
    cached = _result_file(cache_dir, code, day)
    if cached is not None and cached.is_file():
        try:
            return FundDocs.from_json(json.loads(cached.read_text(encoding="utf-8")))
        except (ValueError, KeyError, TypeError):
            pass
    try:
        pages = _Pages(_Fetcher(cfg, manager, client, sleep, monotonic), cache_dir, day)
        if manager.pages:
            got = [pages.get(u, shared=True) for u in manager.pages]
            links = [read_links(_text(body), final) for final, body in got]
            page_url, sha = manager.pages[0], _sha(got[0][1])
        else:
            if manager.template:
                fund_url = _fill(manager.template, code, escape=False)
            else:
                fund_url, list_url, list_body = _find_fund_page(manager, code, pages)
                if fund_url is None:
                    out = result("not_found", page_url=list_url, sha=_sha(list_body),
                                 reason=dict(NOT_IN_LIST), manager=manager)
                    _store(cached, out)
                    return out
            final, body = pages.get(fund_url, shared=False)
            links = [read_links(_text(body), final)]
            page_url, sha = final, _sha(body)
        docs = select_docs(manager, code, links)
        out = result("ok" if docs else "not_found", docs=docs, page_url=page_url, sha=sha,
                     reason=None if docs else dict(NO_LINK), manager=manager)
        _store(cached, out)
        return out
    except _Fail as e:
        return result("failed", reason={"tr": "Belgeler şu an alınamadı.", "en": str(e)},
                      manager=manager)
    except httpx.HTTPError as e:
        return result("failed", reason={"tr": "Belgeler şu an alınamadı.",
                                        "en": f"{type(e).__name__}: {e}"}, manager=manager)
    except Exception as e:      # never raise to the API: a bug is a failed result too
        return result("failed", reason={"tr": "Belgeler şu an alınamadı.",
                                        "en": f"{type(e).__name__}: {e}"}, manager=manager)


def _store(path: Path | None, docs: FundDocs) -> None:
    if path is not None and docs.status in ("ok", "not_found"):
        try:
            _write(path, json.dumps(docs.to_json(), ensure_ascii=False, indent=1))
        except OSError:
            pass
