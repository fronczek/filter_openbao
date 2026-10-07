from ansible.errors import AnsibleFilterError
import os
import json
from functools import lru_cache
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest


def _first_set(*names):
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _normalize_path(path, mount_point):
    raw_path = str(path or "").strip("/")
    mount = str(mount_point or "kv").strip("/")
    if not raw_path:
        raise AnsibleFilterError("openbao requires a non-empty secret path")
    if raw_path.startswith(f"{mount}/"):
        return mount, raw_path[len(mount) + 1 :]
    return mount, raw_path


def _api_get_json(url, headers, timeout):
    req = urlrequest.Request(url=url, headers=headers, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
    except urlerror.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            payload = json.loads(body or "{}")
            errors = payload.get("errors") or []
            details = "; ".join(str(item) for item in errors if item)
        except json.JSONDecodeError:
            details = body.strip()
        raise AnsibleFilterError(f"OpenBao API {exc.code} for {url}: {details or 'no details'}") from exc
    except urlerror.URLError as exc:
        raise AnsibleFilterError(f"OpenBao connection failed for {url}: {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise AnsibleFilterError(f"OpenBao returned invalid JSON for {url}") from exc


def _extract_secret(payload):
    data = payload.get("data")
    if not isinstance(data, dict):
        raise AnsibleFilterError("OpenBao response does not contain data object")
    nested = data.get("data")
    return nested if isinstance(nested, dict) else data


@lru_cache(maxsize=512)
def _read_secret(path, mount_point, version, addr, token, namespace, timeout):
    mount, rel_path = _normalize_path(path, mount_point)
    addr_clean = str(addr).rstrip("/")
    rel_encoded = "/".join(urlparse.quote(part, safe="") for part in rel_path.split("/"))
    mount_encoded = urlparse.quote(mount, safe="")

    headers = {"X-Vault-Token": token, "Accept": "application/json"}
    if namespace:
        headers["X-Vault-Namespace"] = namespace

    v2_url = f"{addr_clean}/v1/{mount_encoded}/data/{rel_encoded}"
    if version is not None:
        v2_url = f"{v2_url}?{urlparse.urlencode({'version': str(version)})}"
    v1_url = f"{addr_clean}/v1/{mount_encoded}/{rel_encoded}"

    # Try KV v2 endpoint first; on path/engine mismatch, fall back to KV v1.
    try:
        return _extract_secret(_api_get_json(v2_url, headers, timeout))
    except AnsibleFilterError as exc:
        message = str(exc)
        if " API 400 " not in message and " API 404 " not in message and " API 405 " not in message:
            raise

    return _extract_secret(_api_get_json(v1_url, headers, timeout))


def openbao(
    path,
    field=None,
    mount_point="kv",
    version=None,
    addr=None,
    token=None,
    namespace=None,
    timeout=10,
):
    addr_value = addr or _first_set("OPENBAO_ADDR", "BAO_ADDR", "VAULT_ADDR")
    token_value = token or _first_set("OPENBAO_TOKEN", "BAO_TOKEN", "VAULT_TOKEN")
    namespace_value = namespace or _first_set("OPENBAO_NAMESPACE", "BAO_NAMESPACE", "VAULT_NAMESPACE")

    if not addr_value:
        raise AnsibleFilterError("OpenBao address not set (OPENBAO_ADDR/BAO_ADDR/VAULT_ADDR)")
    if not token_value:
        raise AnsibleFilterError("OpenBao token not set (OPENBAO_TOKEN/BAO_TOKEN/VAULT_TOKEN)")

    secret = _read_secret(
        str(path),
        str(mount_point),
        version,
        str(addr_value),
        str(token_value),
        str(namespace_value) if namespace_value else None,
        float(timeout),
    )

    if field is None:
        if len(secret) == 1:
            return next(iter(secret.values()))
        keys = ", ".join(sorted(secret.keys()))
        raise AnsibleFilterError(f"field is required for multi-key secret (available: {keys})")

    key = str(field)
    if key not in secret:
        keys = ", ".join(sorted(secret.keys()))
        raise AnsibleFilterError(f"field '{key}' not found (available: {keys})")

    return secret[key]


class FilterModule(object):
    def filters(self):
        return {
            "openbao": openbao
        }
