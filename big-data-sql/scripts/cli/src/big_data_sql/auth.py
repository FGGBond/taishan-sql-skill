from __future__ import annotations

import os
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Iterable

from .config import Settings, load_settings
from . import session_store


class AuthError(RuntimeError):
    """Raised when browser cookies cannot be loaded."""


@dataclass(frozen=True)
class CookieResult:
    browser: str
    domains: tuple[str, ...]
    cookie_header: str
    cookie_count: int
    source: str = "browser"


# scriptcenter 接口强依赖；值会在浏览器访问 dp.jd.com 时轮换
_CRITICAL_SESSION_COOKIES: tuple[str, ...] = ("ssa.bdp",)

_DOMAIN_RANK: dict[str, int] = {
    "scriptcenter.dp.jd.com": 300,
    "ide.scriptcenter.jd.com": 250,
    "dp.jd.com": 200,
    "jd.com": 50,
}

_process_cache: dict[str, CookieResult] = {}
_last_load_source: str = "browser"


def load_browser_cookies(
    settings: Settings | None = None,
    *,
    force_refresh: bool = False,
) -> CookieResult:
    global _last_load_source
    settings = settings or load_settings()

    env_header = os.getenv("BDP_SQL_COOKIE_HEADER", "").strip()
    if env_header:
        result = CookieResult(
            browser="env",
            domains=settings.cookie_domains,
            cookie_header=env_header,
            cookie_count=_count_cookie_pairs(env_header),
            source="env",
        )
        _last_load_source = "env"
        return result

    cache_key = session_store.settings_fingerprint(
        browsers=settings.browsers,
        cookie_domains=settings.cookie_domains,
    )

    if not force_refresh:
        cached = _process_cache.get(cache_key)
        if cached is not None:
            _last_load_source = cached.source
            return cached

        session_data = session_store.load_session(
            browsers=settings.browsers,
            cookie_domains=settings.cookie_domains,
        )
        if session_data is not None:
            cached_header = str(session_data["cookie_header"])
            if not _cached_header_stale(settings, cached_header):
                result = CookieResult(
                    browser=str(session_data.get("browser") or settings.browsers[0]),
                    domains=settings.cookie_domains,
                    cookie_header=cached_header,
                    cookie_count=int(session_data.get("cookie_count") or 0),
                    source="cache",
                )
                _process_cache[cache_key] = result
                _last_load_source = "cache"
                return result
            session_store.clear_session()

    result = _load_from_browser(settings)
    _process_cache[cache_key] = result
    _last_load_source = "browser"
    if session_store.cache_enabled():
        session_store.save_session(
            browsers=settings.browsers,
            cookie_domains=settings.cookie_domains,
            browser=result.browser,
            cookie_header=result.cookie_header,
            cookie_count=result.cookie_count,
        )
    return result


def auth_headers(settings: Settings | None = None, *, force_refresh: bool = False) -> dict[str, str]:
    result = load_browser_cookies(settings, force_refresh=force_refresh)
    return {"Cookie": result.cookie_header}


def invalidate_auth_cache(settings: Settings | None = None) -> None:
    settings = settings or load_settings()
    cache_key = session_store.settings_fingerprint(
        browsers=settings.browsers,
        cookie_domains=settings.cookie_domains,
    )
    _process_cache.pop(cache_key, None)
    session_store.clear_session()


def auth_cache_status(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or load_settings()
    status = session_store.session_status(
        browsers=settings.browsers,
        cookie_domains=settings.cookie_domains,
    )
    status["last_source"] = _last_load_source
    return status


def cookie_value_from_header(cookie_header: str, name: str) -> str:
    prefix = f"{name}="
    for part in cookie_header.split("; "):
        if part.startswith(prefix):
            return part[len(prefix) :]
    return ""


def cookie_fingerprint(value: str, *, head: int = 16, tail: int = 8) -> str:
    if not value:
        return ""
    if len(value) <= head + tail:
        return value
    return f"{value[:head]}...{value[-tail:]}"


def analyze_auth_cookies(
    settings: Settings | None = None,
    *,
    cached_header: str | None = None,
) -> dict[str, object]:
    """Compare cached vs browser cookies for doctor diagnostics."""
    settings = settings or load_settings()
    checks: list[dict[str, object]] = []
    warnings: list[str] = []

    try:
        browser_header = _read_browser_cookie_header(settings)
    except AuthError as exc:
        return {
            "ok": False,
            "message": str(exc),
            "checks": checks,
            "warnings": warnings,
        }

    headers_to_compare: list[tuple[str, str]] = [("browser", browser_header)]
    if cached_header:
        headers_to_compare.insert(0, ("cache", cached_header))

    for cookie_name in _CRITICAL_SESSION_COOKIES:
        browser_value = cookie_value_from_header(browser_header, cookie_name)
        entry: dict[str, object] = {
            "name": cookie_name,
            "browser_fingerprint": cookie_fingerprint(browser_value),
            "browser_length": len(browser_value),
        }
        if cached_header:
            cached_value = cookie_value_from_header(cached_header, cookie_name)
            entry["cache_fingerprint"] = cookie_fingerprint(cached_value)
            entry["cache_length"] = len(cached_value)
            entry["stale"] = bool(browser_value and cached_value and cached_value != browser_value)
            if entry["stale"]:
                warnings.append(
                    f"缓存中的 {cookie_name} 与浏览器不一致，请执行 doctor --refresh-auth"
                )
        if not browser_value:
            warnings.append(f"浏览器未读取到有效 {cookie_name}，请访问 dp.jd.com 在线查询后重试")
        checks.append(entry)

    conflicts = detect_cookie_conflicts(settings)
    if conflicts:
        warnings.append(
            "检测到同名 cookie 在多个域存在不同值，CLI 已按域名优先级选取（scriptcenter.dp.jd.com 优先）"
        )

    return {
        "ok": True,
        "checks": checks,
        "conflicts": conflicts,
        "warnings": warnings,
    }


def detect_cookie_conflicts(settings: Settings | None = None) -> list[dict[str, object]]:
    settings = settings or load_settings()
    conflicts: list[dict[str, object]] = []
    watch = {"JSESSIONID", "SSAID", *_CRITICAL_SESSION_COOKIES}

    for browser in settings.browsers:
        try:
            jar = _load_cookie_jar(browser, settings.cookie_domains)
        except Exception:
            continue
        by_name: dict[str, list[tuple[str, str]]] = {}
        for cookie in jar:
            if cookie.name not in watch:
                continue
            if not _matches_domain(cookie.domain, settings.cookie_domains):
                continue
            value = cookie.value or ""
            if not value:
                continue
            by_name.setdefault(cookie.name, []).append((cookie.domain, value))

        for name, entries in sorted(by_name.items()):
            fingerprints = {cookie_fingerprint(value) for _, value in entries}
            if len(fingerprints) > 1:
                conflicts.append(
                    {
                        "name": name,
                        "browser": browser,
                        "domains": [
                            {
                                "domain": domain,
                                "fingerprint": cookie_fingerprint(value),
                                "length": len(value),
                            }
                            for domain, value in entries
                        ],
                    }
                )
    return conflicts


def _cached_header_stale(settings: Settings, cached_header: str) -> bool:
    try:
        browser_header = _read_browser_cookie_header(settings)
    except AuthError:
        return False

    for name in _CRITICAL_SESSION_COOKIES:
        cached_value = cookie_value_from_header(cached_header, name)
        browser_value = cookie_value_from_header(browser_header, name)
        if browser_value and cached_value != browser_value:
            return True
    return False


def _read_browser_cookie_header(settings: Settings) -> str:
    return _load_from_browser(settings).cookie_header


def _load_from_browser(settings: Settings) -> CookieResult:
    errors: list[str] = []

    for browser in settings.browsers:
        try:
            jar = _load_cookie_jar(browser, settings.cookie_domains)
            cookie_header = _build_cookie_header(jar, settings.cookie_domains)
            if cookie_header:
                return CookieResult(
                    browser=browser,
                    domains=settings.cookie_domains,
                    cookie_header=cookie_header,
                    cookie_count=_count_cookie_pairs(cookie_header),
                    source="browser",
                )
            errors.append(f"{browser}: 未找到匹配域名的 cookie")
        except Exception as exc:  # pragma: no cover - depends on local browser state
            errors.append(f"{browser}: {exc}")

    joined = "; ".join(errors) if errors else "未配置浏览器"
    raise AuthError(f"无法从浏览器读取大数据平台认证 cookie：{joined}")


def _load_cookie_jar(browser: str, domains: tuple[str, ...]) -> CookieJar:
    try:
        import browser_cookie3
    except ImportError as exc:  # pragma: no cover
        raise AuthError("缺少 browser-cookie3 依赖，请先安装项目依赖") from exc

    domain_hint = _cookie_load_domain(domains)
    if browser == "edge":
        return browser_cookie3.edge(domain_name=domain_hint)
    if browser == "chrome":
        return browser_cookie3.chrome(domain_name=domain_hint)
    if browser == "firefox":
        return browser_cookie3.firefox(domain_name=domain_hint)
    if browser == "safari":
        return browser_cookie3.safari(domain_name=domain_hint)
    raise AuthError(f"暂不支持浏览器：{browser}")


def _cookie_load_domain(domains: tuple[str, ...]) -> str | None:
    if any(domain == "jd.com" or domain.endswith(".jd.com") for domain in domains):
        return "jd.com"
    return domains[0] if domains else None


def _build_cookie_header(jar: CookieJar, domains: Iterable[str]) -> str:
    domain_tuple = tuple(domains)
    best: dict[str, tuple[int, str]] = {}

    for cookie in jar:
        if not _matches_domain(cookie.domain, domain_tuple):
            continue
        value = cookie.value or ""
        if not value:
            continue
        priority = _cookie_priority(cookie.domain)
        current = best.get(cookie.name)
        if current is None or priority > current[0]:
            best[cookie.name] = (priority, value)

    return "; ".join(f"{name}={value}" for name, (_, value) in best.items())


def _cookie_priority(cookie_domain: str) -> int:
    host = cookie_domain.lstrip(".").lower()
    if cookie_domain.startswith("."):
        return _DOMAIN_RANK.get(host, 40)
    return _DOMAIN_RANK.get(host, 0)


def _matches_domain(cookie_domain: str, domains: tuple[str, ...]) -> bool:
    normalized = cookie_domain.lstrip(".").lower()
    allowed_hosts = {domain.lower() for domain in domains if domain != "jd.com"}

    if normalized in allowed_hosts:
        return True

    if cookie_domain.startswith("."):
        parent = normalized
        return any(host == parent or host.endswith(f".{parent}") for host in allowed_hosts)

    return False


def _count_cookie_pairs(cookie_header: str) -> int:
    return len([part for part in cookie_header.split("; ") if "=" in part])
