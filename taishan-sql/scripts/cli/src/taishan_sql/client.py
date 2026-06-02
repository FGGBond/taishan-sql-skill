from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .auth import AuthError, auth_headers
from .config import Settings, load_settings
from .normalize import failure, normalize_api_response
from .specs import ApiSpec, load_spec


class TaishanClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    def call(self, spec_name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        params = params or {}
        spec = load_spec(spec_name, self.settings)
        started = time.monotonic()

        try:
            request = self._build_request(spec, params)
            with urlopen(request, timeout=self._timeout_for(spec)) as response:
                body = response.read().decode("utf-8")
        except ValueError as exc:
            return failure("INVALID_ARGUMENT", str(exc), recoverable=False)
        except AuthError as exc:
            return failure("AUTH_UNAVAILABLE", str(exc))
        except HTTPError as exc:
            return failure("HTTP_ERROR", f"HTTP {exc.code}: {exc.reason}", status=exc.code)
        except URLError as exc:
            return failure("NETWORK_ERROR", str(exc.reason))
        except TimeoutError as exc:
            return failure("TIMEOUT", str(exc))

        elapsed_ms = round((time.monotonic() - started) * 1000)
        try:
            raw = json.loads(body)
        except json.JSONDecodeError:
            return failure("INVALID_JSON", "接口返回不是有效 JSON", body=body, elapsed_ms=elapsed_ms)

        normalized = normalize_api_response(spec.raw, raw)
        normalized["elapsed_ms"] = elapsed_ms
        normalized["tool"] = spec.name
        return normalized

    def _build_request(self, spec: ApiSpec, params: dict[str, Any]) -> Request:
        query_params = self._query_params(spec, params)
        base_url = self._base_url(spec, params)
        url = f"{base_url}{spec.endpoint_path}"
        if query_params:
            url = f"{url}?{urlencode(query_params)}"

        headers = self._headers(spec, base_url)
        body = self._body(spec, params)
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")

        return Request(url, data=data, headers=headers, method=spec.method)

    def _query_params(self, spec: ApiSpec, params: dict[str, Any]) -> dict[str, Any]:
        query_spec = spec.raw.get("query", {})
        query: dict[str, Any] = {"_t": int(time.time() * 1000)}

        for key, definition in query_spec.items():
            if isinstance(definition, dict) and "value" in definition:
                query[key] = definition["value"]
            elif isinstance(definition, dict) and "param" in definition:
                param_name = definition["param"]
                if definition.get("required") and param_name not in params:
                    raise ValueError(f"缺少必要参数：{param_name}")
                if param_name in params and params[param_name] is not None:
                    query[key] = params[param_name]
            else:
                query[key] = definition

        return query

    def _base_url(self, spec: ApiSpec, params: dict[str, Any]) -> str:
        environment = str(params.get("environment") or params.get("env") or "prod")
        environments = spec.raw.get("environments", {})
        if environments:
            if environment not in environments:
                allowed = ", ".join(sorted(environments.keys()))
                raise ValueError(f"不支持的环境：{environment}，可选值：{allowed}")
            return str(environments[environment]["base_url"]).rstrip("/")
        return spec.base_url

    def _headers(self, spec: ApiSpec, base_url: str) -> dict[str, str]:
        headers = {str(k): str(v) for k, v in spec.raw.get("headers", {}).items()}
        if spec.raw.get("auth", {}).get("provider") == "browser_cookie":
            host = urlparse(base_url).hostname
            settings = replace(self.settings, cookie_domains=(host,)) if host else self.settings
            headers.update(auth_headers(settings))
        return headers

    def _body(self, spec: ApiSpec, params: dict[str, Any]) -> dict[str, Any] | None:
        body_spec = spec.raw.get("request", {}).get("body")
        if not body_spec:
            return None

        body: dict[str, Any] = {}
        for key, definition in body_spec.items():
            param_name = definition.get("param", key)
            if param_name in params and params[param_name] is not None:
                body[key] = params[param_name]
            elif "default" in definition:
                body[key] = definition["default"]
            elif definition.get("required"):
                raise ValueError(f"缺少必要参数：{param_name}")
        return body

    def _timeout_for(self, spec: ApiSpec) -> int:
        return int(spec.raw.get("safety", {}).get("timeout_seconds", self.settings.timeout_seconds))
