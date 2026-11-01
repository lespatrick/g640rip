"""Bonjour / mDNS and CUPS discovery for Canon G640 printers on macOS."""

import fcntl
import os
import re
import socket
import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse


@dataclass
class PrinterInfo:
    name: str
    host: str
    port: int = 631
    ip_address: Optional[str] = None
    resource_path: str = "ipp/print"
    is_tls: bool = False
    cups_queue: Optional[str] = None
    txt_records: Dict[str, str] = field(default_factory=dict)
    formats: List[str] = field(default_factory=list)
    urf_features: Dict[str, str] = field(default_factory=dict)

    @property
    def ipp_url(self) -> str:
        scheme = "ipps" if self.is_tls else "ipp"
        # Always prioritize IP address to avoid mDNS resolution/space issues
        target = self.ip_address or self.host
        # Ensure no spaces in URL target
        target = urllib.parse.quote(target.strip())
        path = self.resource_path.lstrip("/")
        return f"{scheme}://{target}:{self.port}/{path}"

    @property
    def http_url(self) -> str:
        scheme = "https" if self.is_tls else "http"
        target = self.ip_address or self.host
        target = urllib.parse.quote(target.strip())
        path = self.resource_path.lstrip("/")
        return f"{scheme}://{target}:{self.port}/{path}"

    @property
    def supports_urf(self) -> bool:
        return "image/urf" in self.formats or "URF" in self.txt_records

    @property
    def supports_pwg(self) -> bool:
        return "image/pwg-raster" in self.formats


def _parse_txt_records(raw_txt: str) -> Dict[str, str]:
    """Parse key=value pairs from mDNS TXT record string."""
    records: Dict[str, str] = {}
    tokens = re.split(r"\s+(?=[a-zA-Z0-9_]+(?:=|$))", raw_txt.strip())
    for token in tokens:
        if "=" in token:
            k, v = token.split("=", 1)
            records[k.strip()] = v.strip().strip('"').strip("'")
        elif token:
            records[token.strip()] = ""
    return records


def _parse_urf_field(urf_str: str) -> Dict[str, str]:
    """Parse URF capabilities string, e.g., 'V1.4,CP1,PQ3-5,RS600,SRGB24,W8'."""
    features = {}
    for part in urf_str.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("V"):
            features["version"] = part[1:]
        elif part.startswith("RS"):
            features["resolution"] = part[2:]
        elif part.startswith("PQ"):
            features["quality"] = part[2:]
        elif part.startswith("CP"):
            features["copies"] = part[2:]
        elif part in ("SRGB24", "W8", "RGB24", "ADOBE_RGB_16"):
            features.setdefault("colorspaces", []).append(part)
        else:
            features[part] = "true"
    return features


def resolve_mdns_host_ipv4(hostname: str, timeout_sec: float = 1.5) -> Optional[str]:
    """Resolve mDNS hostname (e.g. cA5AB8400000.local.) to IPv4 address using dns-sd."""
    clean_host = hostname.rstrip(".")
    # First try standard socket gethostbyname
    try:
        ip = socket.gethostbyname(clean_host)
        if ip:
            return ip
    except Exception:
        pass

    # Use dns-sd -G v4 with non-blocking I/O
    try:
        proc = subprocess.Popen(
            ["dns-sd", "-G", "v4", clean_host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        fl = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        t_end = time.time() + timeout_sec
        raw_bytes = b""
        while time.time() < t_end:
            try:
                chunk = proc.stdout.read(4096)
                if chunk:
                    raw_bytes += chunk
                    text = raw_bytes.decode("utf-8", errors="replace")
                    match = re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", text)
                    if match:
                        proc.terminate()
                        proc.wait()
                        return match.group(1)
            except BlockingIOError:
                pass
            time.sleep(0.05)
        proc.terminate()
        proc.wait()
    except Exception:
        pass

    return None


def lookup_service_instance(instance_name: str, service_type: str = "_ipp._tcp", timeout_sec: float = 1.5) -> Optional[PrinterInfo]:
    """Lookup specific Bonjour service instance to get host, port, TXT records."""
    try:
        proc = subprocess.Popen(
            ["dns-sd", "-L", instance_name, service_type, "local."],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        fl = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
        fcntl.fcntl(proc.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)

        t_end = time.time() + timeout_sec
        raw_bytes = b""
        while time.time() < t_end:
            try:
                chunk = proc.stdout.read(4096)
                if chunk:
                    raw_bytes += chunk
                    if b"can be reached at" in raw_bytes and b"rp=" in raw_bytes:
                        break
            except BlockingIOError:
                pass
            time.sleep(0.05)
        proc.terminate()
        proc.wait()

        full_text = raw_bytes.decode("utf-8", errors="replace")
        reach_match = re.search(r"can be reached at\s+([^:]+):(\d+)", full_text)
        if not reach_match:
            return None

        host = reach_match.group(1).rstrip(".")
        port = int(reach_match.group(2))

        # Extract TXT records
        txt_records = _parse_txt_records(full_text)
        rp = txt_records.get("rp", "ipp/print")
        pdl_raw = txt_records.get("pdl", "")
        formats = [fmt.strip() for fmt in pdl_raw.split(",") if fmt.strip()]
        urf_raw = txt_records.get("URF", "")
        urf_features = _parse_urf_field(urf_raw) if urf_raw else {}

        # Resolve IPv4
        ip_addr = resolve_mdns_host_ipv4(host)
        is_tls = "_ipps" in service_type

        return PrinterInfo(
            name=instance_name,
            host=host,
            port=port,
            ip_address=ip_addr,
            resource_path=rp,
            is_tls=is_tls,
            txt_records=txt_records,
            formats=formats,
            urf_features=urf_features,
        )
    except Exception:
        return None


def discover_canon_printers(timeout_sec: float = 1.5, model_filter: str = "G60") -> List[PrinterInfo]:
    """Discover Canon G600 / G640 printers via mDNS and CUPS device list."""
    printers: List[PrinterInfo] = []
    found_names = set()

    # Step 1: Browse mDNS for _ipp._tcp and _ipps._tcp
    for stype in ("_ipp._tcp", "_ipps._tcp"):
        try:
            proc = subprocess.Popen(
                ["dns-sd", "-B", stype, "local."],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            fl = fcntl.fcntl(proc.stdout, fcntl.F_GETFL)
            fcntl.fcntl(proc.stdout, fcntl.F_SETFL, fl | os.O_NONBLOCK)

            t_end = time.time() + timeout_sec
            raw_bytes = b""
            while time.time() < t_end:
                try:
                    chunk = proc.stdout.read(4096)
                    if chunk:
                        raw_bytes += chunk
                        lines = raw_bytes.decode("utf-8", errors="replace").splitlines()
                        for line in lines:
                            if "Add" in line and (model_filter.lower() in line.lower() or "canon" in line.lower()):
                                parts = line.strip().split()
                                if len(parts) >= 7:
                                    instance_name = " ".join(parts[6:])
                                    if instance_name not in found_names:
                                        found_names.add(instance_name)
                                        p_info = lookup_service_instance(instance_name, service_type=stype, timeout_sec=1.5)
                                        if p_info:
                                            printers.append(p_info)
                except BlockingIOError:
                    pass
                time.sleep(0.05)
            proc.terminate()
            proc.wait()
        except Exception:
            pass

    # Step 2: Fallback / enrichment from local CUPS
    cups_printers = probe_cups_for_canon(model_filter=model_filter)
    for cp in cups_printers:
        # Match by IP or name
        already_present = any(
            (p.ip_address and p.ip_address == cp.ip_address) or (p.name == cp.name)
            for p in printers
        )
        if not already_present:
            printers.append(cp)

    return printers


def probe_cups_for_canon(model_filter: str = "G60") -> List[PrinterInfo]:
    """Probe CUPS configuration for registered Canon G600 series printers."""
    results: List[PrinterInfo] = []
    try:
        out = subprocess.check_output(["lpstat", "-v"], text=True)
        for line in out.splitlines():
            if model_filter.lower() in line.lower() or "canon" in line.lower():
                m = re.match(r"^device for ([^:]+):\s+(.*)$", line.strip())
                if m:
                    pname, raw_uri = m.group(1), m.group(2)
                    is_tls = "_ipps" in raw_uri or "https" in raw_uri

                    # Extract service name from dnssd:// URI if present
                    # Format: dnssd://Canon%20G600%20series._ipps._tcp.local./...
                    host = None
                    port = 631
                    ip = None
                    service_match = re.match(r"^dnssd://([^/]+)", raw_uri)
                    if service_match:
                        raw_srv = service_match.group(1).rstrip(".")
                        for sfx in ["._ipps._tcp.local", "._ipp._tcp.local", "._ipps._tcp", "._ipp._tcp"]:
                            if raw_srv.endswith(sfx):
                                raw_srv = raw_srv[:-len(sfx)]
                                break
                        service_name = urllib.parse.unquote(raw_srv)
                        # Resolve service via Bonjour
                        resolved = lookup_service_instance(service_name, service_type="_ipps._tcp" if is_tls else "_ipp._tcp")
                        if not resolved:
                            resolved = lookup_service_instance(service_name, service_type="_ipp._tcp")

                        if resolved:
                            host = resolved.host
                            port = resolved.port
                            ip = resolved.ip_address

                    if not host:
                        # Fallback to direct resolution or known IP
                        ip = resolve_mdns_host_ipv4("cA5AB8400000.local") or "192.168.0.41"
                        host = ip

                    info = PrinterInfo(
                        name=pname,
                        host=host or "192.168.0.41",
                        port=port,
                        ip_address=ip or "192.168.0.41",
                        resource_path="ipp/print",
                        is_tls=is_tls,
                        cups_queue=pname,
                        formats=["image/urf", "image/pwg-raster"],
                    )
                    results.append(info)
    except Exception:
        pass
    return results
