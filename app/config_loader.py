from pathlib import Path
from urllib.parse import urlparse

import yaml

def _unique_display_name_from_host(hostname, used_counts):
    if not hostname:
        return None
    base = hostname.lower()
    n = used_counts.get(base, 0)
    used_counts[base] = n + 1
    if n == 0:
        return base
    return f"{base}-{n + 1}"

def _coerce_mixed_services_list(items):
    if not items:
        return []
    used = {}
    out = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            u = item.strip()
            if not u.startswith(("http://", "https://")):
                raise ValueError(
                    f"Invalid service entry (expected http(s) URL or mapping with url): {item!r}"
                )
            parsed = urlparse(u)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"Invalid URL: {u!r}")
            host = parsed.hostname
            name = _unique_display_name_from_host(host, used)
            if not name:
                name = f"instance-{len(out) + 1}"
            out.append({"name": name, "url": u})
            continue
        if isinstance(item, dict):
            url = item.get("url")
            if not url:
                raise ValueError(f"Service entry missing url: {item!r}")
            url = str(url).strip()
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                raise ValueError(f"Invalid url in service entry: {url!r}")
            name = item.get("name")
            if name is None or (isinstance(name, str) and not name.strip()):
                host = parsed.hostname
                name = _unique_display_name_from_host(host, used)
                if not name:
                    name = f"instance-{len(out) + 1}"
            else:
                name = str(name).strip()
            out.append({"name": name, "url": url})
            continue
        raise ValueError(f"Invalid service entry type: {type(item).__name__}")
    return out

def _services_from_parsed_data(data):
    if isinstance(data, list):
        return _coerce_mixed_services_list(data)
    if isinstance(data, dict):
        if "services" in data:
            return _coerce_mixed_services_list(data["services"])
        if "urls" in data:
            return _coerce_mixed_services_list(data["urls"])
    return []

def _urls_from_plain_lines(text):
    lines = [
        ln.strip()
        for ln in text.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return None
    if not all(
        ln.startswith(("http://", "https://")) for ln in lines
    ):
        return None
    return _coerce_mixed_services_list(lines)

def load_services_from_file(path):
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    if raw.strip():
        plain = _urls_from_plain_lines(raw)
        if plain is not None:
            return plain
    data = yaml.safe_load(raw)
    if isinstance(data, str) and data.strip().startswith(("http://", "https://")):
        return _coerce_mixed_services_list([data.strip()])
    if data is None:
        return []
    return _services_from_parsed_data(data)

_INSTANCES_PATHS = ("/config/instances.yaml", "config/instances.yaml")

def load_services():
    for path in _INSTANCES_PATHS:
        if Path(path).is_file():
            return load_services_from_file(path)
    tried = ", ".join(_INSTANCES_PATHS)
    raise FileNotFoundError(
        f"instances.yaml not found (tried: {tried}). "
        "Create config/instances.yaml or mount the file at /config/instances.yaml in Docker."
    )
