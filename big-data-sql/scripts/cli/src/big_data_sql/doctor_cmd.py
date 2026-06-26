from __future__ import annotations

from typing import Any

from .account_config import extract_markets
from .auth import (
    AuthError,
    CookieResult,
    analyze_auth_cookies,
    auth_cache_status,
    cookie_value_from_header,
    invalidate_auth_cache,
    load_browser_cookies,
)
from .client import PlatformClient
from .config import Settings, load_settings
from . import session_store
from .normalize import failure, success
from .profile_store import profile_status
from .project_info import extract_local_project
from .user_info import extract_erp

DOCTOR_API_PROBES: tuple[dict[str, str], ...] = (
    {"name": "loginUser", "path": "/request/portal/common/loginUser"},
    {"name": "getErpLocalProject", "path": "/scriptcenter/project/getErpLocalProject.ajax"},
    {"name": "getMarketByErp", "path": "/scriptcenter/config/getMarketByErp.ajax"},
)

_SCRIPT_CENTER_APIS = frozenset({"getErpLocalProject", "getMarketByErp"})


def summarize_api_check(name: str, path: str, resp: dict[str, Any]) -> dict[str, Any]:
    check: dict[str, Any] = {"name": name, "path": path}
    if resp.get("error_code"):
        check["ok"] = False
        check["error_code"] = resp.get("error_code")
        check["message"] = str(resp.get("message") or "接口请求失败")
        if resp.get("status") is not None:
            check["status"] = resp.get("status")
        return check

    if name == "loginUser":
        erp = extract_erp(resp)
        if erp:
            check["ok"] = True
            check["erp"] = erp
            return check
        check["ok"] = False
        check["error_code"] = "API_ERROR"
        check["message"] = str(resp.get("message") or resp.get("msg") or "无法解析 ERP")
        return check

    if name == "getErpLocalProject":
        project = extract_local_project(resp)
        if project:
            check["ok"] = True
            check["git_project_id"] = project["git_project_id"]
            return check
        check["ok"] = False
        check["error_code"] = "API_ERROR"
        check["message"] = str(resp.get("message") or resp.get("msg") or "无法获取本地代码库")
        return check

    if name == "getMarketByErp":
        markets = extract_markets(resp)
        check["ok"] = True
        check["market_count"] = len(markets)
        return check

    check["ok"] = True
    return check


def probe_platform_apis(client: PlatformClient) -> list[dict[str, Any]]:
    login_resp = client.get_login_user(track=False)
    project_resp = client.get_erp_local_project(track=False)
    markets_resp = client.get_markets_by_erp(track=False)
    return [
        summarize_api_check("loginUser", DOCTOR_API_PROBES[0]["path"], login_resp),
        summarize_api_check("getErpLocalProject", DOCTOR_API_PROBES[1]["path"], project_resp),
        summarize_api_check("getMarketByErp", DOCTOR_API_PROBES[2]["path"], markets_resp),
    ]


def doctor_verdict(
    checks: list[dict[str, Any]],
    *,
    cookie_warnings: list[str] | None = None,
) -> tuple[bool, str | None, str | None]:
    failed = [check for check in checks if not check.get("ok")]
    if not failed:
        return True, None, None

    failed_names = [str(check["name"]) for check in failed]
    stale_hint = ""
    if cookie_warnings and any("ssa.bdp" in warning for warning in cookie_warnings):
        stale_hint = "检测到 ssa.bdp 会话 cookie 与浏览器不一致（常见于缓存过期），"

    if "loginUser" in failed_names:
        detail = _failed_api_detail(failed)
        return (
            False,
            "AUTH_UNAVAILABLE",
            f"门户登录态无效：{detail}。请在 Edge/Chrome 登录 dp.jd.com 后执行 doctor --refresh-auth",
        )

    script_center_failed = [name for name in failed_names if name in _SCRIPT_CENTER_APIS]
    if script_center_failed:
        detail = _failed_api_detail(failed)
        return (
            False,
            "SCRIPT_CENTER_UNAVAILABLE",
            (
                f"{stale_hint}脚本中心接口不可用：{detail}。"
                "请先在浏览器打开 dp.jd.com 在线查询，再执行 doctor --refresh-auth；"
                "若浏览器正常而 CLI 仍失败，可设置 BDP_SQL_COOKIE_HEADER 临时注入 DevTools 复制的 Cookie。"
            ),
        )

    return False, "PLATFORM_UNAVAILABLE", _failed_api_detail(failed)


def _failed_api_detail(failed: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for check in failed:
        name = str(check.get("name") or "unknown")
        message = str(check.get("message") or check.get("error_code") or "失败")
        parts.append(f"{name}({message})")
    return "；".join(parts)


def _failed_api_names(checks: list[dict[str, Any]]) -> list[str]:
    return [str(check["name"]) for check in checks if not check.get("ok")]


def _warnings_from_checks(
    checks: list[dict[str, Any]],
    cookie_analysis: dict[str, object] | None = None,
) -> list[str]:
    warnings: list[str] = []
    for check in checks:
        if check.get("name") == "getMarketByErp" and check.get("ok") and check.get("market_count") == 0:
            warnings.append("getMarketByErp 返回空集市列表，init/list-targets 可能因无可用目标而失败")
    if cookie_analysis:
        for item in cookie_analysis.get("warnings") or []:
            warnings.append(str(item))
    return warnings


def _cached_header_for_analysis(settings: Settings, cookie_result: CookieResult) -> str | None:
    if cookie_result.source == "cache":
        return cookie_result.cookie_header
    session_data = session_store.load_session(
        browsers=settings.browsers,
        cookie_domains=settings.cookie_domains,
    )
    if session_data:
        return str(session_data.get("cookie_header") or "") or None
    return None


def run_doctor(
    settings: Settings | None = None,
    *,
    force_refresh: bool = False,
    public_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = settings or load_settings()
    public_settings = public_settings or {}

    cached_header_before = None
    if not force_refresh:
        session_data = session_store.load_session(
            browsers=settings.browsers,
            cookie_domains=settings.cookie_domains,
        )
        if session_data:
            cached_header_before = str(session_data.get("cookie_header") or "") or None

    try:
        cookie_result = load_browser_cookies(settings, force_refresh=force_refresh)
    except AuthError as exc:
        return failure(
            "AUTH_UNAVAILABLE",
            str(exc),
            settings=public_settings,
            auth_cache=auth_cache_status(settings),
            api_checks=[],
            failed_apis=[],
            cookie_checks=[],
        )

    cookie_analysis = analyze_auth_cookies(
        settings,
        cached_header=cached_header_before or cookie_result.cookie_header,
    )
    cookie_warnings = [str(item) for item in cookie_analysis.get("warnings") or []]

    api_checks = probe_platform_apis(PlatformClient(settings))
    ok, error_code, message = doctor_verdict(api_checks, cookie_warnings=cookie_warnings)
    failed_apis = _failed_api_names(api_checks)

    if not ok and not force_refresh and (
        error_code in {"AUTH_UNAVAILABLE", "SCRIPT_CENTER_UNAVAILABLE"}
        or any("ssa.bdp" in warning for warning in cookie_warnings)
    ):
        invalidate_auth_cache(settings)
        try:
            cookie_result = load_browser_cookies(settings, force_refresh=True)
        except AuthError as exc:
            return failure(
                str(error_code or "AUTH_UNAVAILABLE"),
                str(message or str(exc)),
                settings=public_settings,
                auth_cache=auth_cache_status(settings),
                api_checks=api_checks,
                failed_apis=failed_apis,
                cookie_checks=cookie_analysis.get("checks") or [],
            )
        cookie_analysis = analyze_auth_cookies(settings, cached_header=None)
        cookie_warnings = [str(item) for item in cookie_analysis.get("warnings") or []]
        api_checks = probe_platform_apis(PlatformClient(settings))
        ok, error_code, message = doctor_verdict(api_checks, cookie_warnings=cookie_warnings)
        failed_apis = _failed_api_names(api_checks)

    prof = profile_status()
    common = {
        "auth": {
            "browser": cookie_result.browser,
            "cookie_count": cookie_result.cookie_count,
            "cookie_domains": cookie_result.domains,
            "cookie_source": cookie_result.source,
            "ssa_bdp_fingerprint": _ssa_bdp_fingerprint(cookie_result.cookie_header),
            "auth_cache": auth_cache_status(settings),
        },
        "profile": prof,
        "settings": public_settings,
        "api_checks": api_checks,
        "failed_apis": failed_apis,
        "cookie_checks": cookie_analysis.get("checks") or [],
        "cookie_conflicts": cookie_analysis.get("conflicts") or [],
    }

    if not ok:
        return failure(
            str(error_code or "PLATFORM_UNAVAILABLE"),
            str(message or "平台接口检查未通过"),
            recoverable=error_code in {"AUTH_UNAVAILABLE", "AUTH_EXPIRED", "SCRIPT_CENTER_UNAVAILABLE"},
            **common,
        )

    login_check = next(check for check in api_checks if check["name"] == "loginUser")
    project_check = next(check for check in api_checks if check["name"] == "getErpLocalProject")
    erp = str(login_check.get("erp") or "")
    git_project_id = str(project_check.get("git_project_id") or "")
    git_project = None
    if git_project_id:
        git_project = {"git_project_id": git_project_id}

    warnings = _warnings_from_checks(api_checks, cookie_analysis)
    return success(
        status="ready",
        message="认证与平台接口检查通过" if not warnings else "认证与平台接口检查通过（存在警告）",
        erp=erp,
        git_project=git_project,
        warnings=warnings,
        next_action="init" if not prof.get("initialized") else "run",
        **common,
    )


def _ssa_bdp_fingerprint(cookie_header: str) -> str:
    from .auth import cookie_fingerprint

    return cookie_fingerprint(cookie_value_from_header(cookie_header, "ssa.bdp"))
