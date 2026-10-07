from ansible.errors import AnsibleFilterError
import json
import math
import os
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
        details = body.strip()
        try:
            payload = json.loads(body or "{}")
            if isinstance(payload, dict):
                errors = payload.get("errors") or []
                if isinstance(errors, list):
                    details = "; ".join(str(item) for item in errors if item)
        except json.JSONDecodeError:
            pass
        raise AnsibleFilterError(f"OpenBao API {exc.code} for {url}: {details or 'no details'}") from exc
    except urlerror.URLError as exc:
        raise AnsibleFilterError(f"OpenBao connection failed for {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise AnsibleFilterError(f"OpenBao request timed out for {url}") from exc
    except json.JSONDecodeError as exc:
        raise AnsibleFilterError(f"OpenBao returned invalid JSON for {url}") from exc


def _extract_secret(payload, kv_version):
    if not isinstance(payload, dict):
        raise AnsibleFilterError("OpenBao response is not a JSON object")

    data = payload.get("data")
    if not isinstance(data, dict):
        raise AnsibleFilterError("OpenBao response does not contain data object")

    if kv_version == 1:
        return data

    secret = data.get("data")
    if not isinstance(secret, dict):
        raise AnsibleFilterError("OpenBao KV v2 response does not contain nested data object")
    return secret


def _read_secret(path, mount_point, kv_version, version, addr, token, namespace, timeout):
    mount, rel_path = _normalize_path(path, mount_point)
    addr_clean = str(addr).rstrip("/")
    rel_encoded = "/".join(urlparse.quote(part, safe="") for part in rel_path.split("/"))
    mount_encoded = "/".join(urlparse.quote(part, safe="") for part in mount.split("/"))

    headers = {"X-Vault-Token": token, "Accept": "application/json"}
    if namespace:
        headers["X-Vault-Namespace"] = namespace

    if kv_version == 1:
        url = f"{addr_clean}/v1/{mount_encoded}/{rel_encoded}"
    else:
        url = f"{addr_clean}/v1/{mount_encoded}/data/{rel_encoded}"
        if version is not None:
            url = f"{url}?{urlparse.urlencode({'version': str(version)})}"

    return _extract_secret(_api_get_json(url, headers, timeout), kv_version)


def openbao(
    path,
    field=None,
    mount_point="kv",
    version=None,
    addr=None,
    token=None,
    namespace=None,
    timeout=10,
    kv_version=2,
):
    addr_value = addr or _first_set("OPENBAO_ADDR", "BAO_ADDR", "VAULT_ADDR")
    token_value = token or _first_set("OPENBAO_TOKEN", "BAO_TOKEN", "VAULT_TOKEN")
    namespace_value = namespace or _first_set("OPENBAO_NAMESPACE", "BAO_NAMESPACE", "VAULT_NAMESPACE")

    if not addr_value:
        raise AnsibleFilterError("OpenBao address not set (OPENBAO_ADDR/BAO_ADDR/VAULT_ADDR)")
    if not token_value:
        raise AnsibleFilterError("OpenBao token not set (OPENBAO_TOKEN/BAO_TOKEN/VAULT_TOKEN)")

    if isinstance(kv_version, str):
        kv_version_text = kv_version.strip()
    elif isinstance(kv_version, int) and not isinstance(kv_version, bool):
        kv_version_text = str(kv_version)
    else:
        raise AnsibleFilterError("kv_version must be 1 or 2")
    if kv_version_text not in ("1", "2"):
        raise AnsibleFilterError("kv_version must be 1 or 2")
    kv_version_value = int(kv_version_text)
    if kv_version_value == 1 and version is not None:
        raise AnsibleFilterError("version is only supported for KV v2")

    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError) as exc:
        raise AnsibleFilterError("timeout must be a positive number") from exc
    if not math.isfinite(timeout_value) or timeout_value <= 0:
        raise AnsibleFilterError("timeout must be a positive number")

    secret = _read_secret(
        str(path),
        str(mount_point),
        kv_version_value,
        version,
        str(addr_value),
        str(token_value),
        str(namespace_value) if namespace_value else None,
        timeout_value,
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
