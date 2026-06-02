from __future__ import annotations

from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Iterable

from .config import Settings, load_settings


class AuthError(RuntimeError):
    """Raised when browser cookies cannot be loaded."""


@dataclass(frozen=True)
class CookieResult:
    browser: str
    domains: tuple[str, ...]
    cookie_header: str
    cookie_count: int


def load_browser_cookies(settings: Settings | None = None) -> CookieResult:
    settings = settings or load_settings()
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
                    cookie_count=len([p for p in cookie_header.split("; ") if p]),
                )
            errors.append(f"{browser}: 未找到匹配域名的 cookie")
        except Exception as exc:  # pragma: no cover - depends on local browser state
            errors.append(f"{browser}: {exc}")

    joined = "; ".join(errors) if errors else "未配置浏览器"
    raise AuthError(f"无法从浏览器读取大数据平台认证 cookie：{joined}")


def auth_headers(settings: Settings | None = None) -> dict[str, str]:
    result = load_browser_cookies(settings)
    return {"Cookie": result.cookie_header}


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
    pairs: list[str] = []
    seen: set[str] = set()

    for cookie in jar:
        if not _matches_domain(cookie.domain, domain_tuple):
            continue
        if cookie.name in seen:
            continue
        seen.add(cookie.name)
        pairs.append(f"{cookie.name}={cookie.value}")

    return "; ".join(pairs)


def _matches_domain(cookie_domain: str, domains: tuple[str, ...]) -> bool:
    normalized = cookie_domain.lstrip(".").lower()
    return any(domain == normalized or domain.endswith(f".{normalized}") for domain in domains)
