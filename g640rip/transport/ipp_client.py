"""Pure-Python IPP 2.0 client for querying printer attributes and submitting raw print jobs."""

import io
import os
import re
import ssl
import struct
import subprocess
import tempfile
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple, Union

from .constants import (
    IPP_OP_CANCEL_JOB,
    IPP_OP_GET_PRINTER_ATTRIBUTES,
    IPP_OP_PRINT_JOB,
    IPP_OP_VALIDATE_JOB,
    IPP_VERSION_2_0,
    PRINT_QUALITY_HIGH,
    STATUS_OK,
    TAG_BOOLEAN,
    TAG_CHARSET,
    TAG_END_OF_ATTRIBUTES,
    TAG_ENUM,
    TAG_INTEGER,
    TAG_JOB_ATTRIBUTES,
    TAG_KEYWORD,
    TAG_MIME_MEDIA_TYPE,
    TAG_NAME_WITHOUT_LANGUAGE,
    TAG_NATURAL_LANGUAGE,
    TAG_OPERATION_ATTRIBUTES,
    TAG_PRINTER_ATTRIBUTES,
    TAG_RESOLUTION,
    TAG_TEXT_WITHOUT_LANGUAGE,
    TAG_UNKNOWN,
    TAG_UNSUPPORTED,
    TAG_URI,
)


class IPPAttribute:
    def __init__(self, tag: int, name: str, value: Any):
        self.tag = tag
        self.name = name
        self.value = value

    def __repr__(self) -> str:
        return f"IPPAttribute({self.name}={self.value!r}, tag=0x{self.tag:02x})"


class IPPMessage:
    def __init__(
        self,
        version: Tuple[int, int] = IPP_VERSION_2_0,
        operation_or_status: int = IPP_OP_GET_PRINTER_ATTRIBUTES,
        request_id: int = 1,
    ):
        self.version = version
        self.operation_or_status = operation_or_status
        self.request_id = request_id
        self.operation_attributes: List[IPPAttribute] = []
        self.job_attributes: List[IPPAttribute] = []
        self.printer_attributes: List[IPPAttribute] = []
        self.unsupported_attributes: List[IPPAttribute] = []
        self.data: bytes = b""

    def add_operation_attr(self, tag: int, name: str, value: Any):
        self.operation_attributes.append(IPPAttribute(tag, name, value))

    def add_job_attr(self, tag: int, name: str, value: Any):
        self.job_attributes.append(IPPAttribute(tag, name, value))

    def encode(self) -> bytes:
        """Encode the message into binary IPP wire format."""
        buf = io.BytesIO()
        # Version (2 bytes)
        buf.write(struct.pack("!BB", self.version[0], self.version[1]))
        # Operation-ID / Status Code (2 bytes)
        buf.write(struct.pack("!H", self.operation_or_status))
        # Request-ID (4 bytes)
        buf.write(struct.pack("!I", self.request_id))

        def write_attr_group(group_tag: int, attrs: List[IPPAttribute]):
            if not attrs:
                return
            buf.write(struct.pack("!B", group_tag))
            for attr in attrs:
                buf.write(struct.pack("!B", attr.tag))
                name_bytes = attr.name.encode("utf-8")
                buf.write(struct.pack("!H", len(name_bytes)))
                buf.write(name_bytes)
                val_bytes = self._encode_value(attr.tag, attr.value)
                buf.write(struct.pack("!H", len(val_bytes)))
                buf.write(val_bytes)

        write_attr_group(TAG_OPERATION_ATTRIBUTES, self.operation_attributes)
        write_attr_group(TAG_JOB_ATTRIBUTES, self.job_attributes)
        write_attr_group(TAG_PRINTER_ATTRIBUTES, self.printer_attributes)

        # End tag
        buf.write(struct.pack("!B", TAG_END_OF_ATTRIBUTES))

        # Payload
        if self.data:
            buf.write(self.data)

        return buf.getvalue()

    @staticmethod
    def _encode_value(tag: int, val: Any) -> bytes:
        if tag in (TAG_INTEGER, TAG_ENUM):
            return struct.pack("!i", int(val))
        elif tag == TAG_BOOLEAN:
            return struct.pack("!B", 1 if val else 0)
        elif tag == TAG_RESOLUTION:
            if isinstance(val, (tuple, list)) and len(val) >= 2:
                units = val[2] if len(val) > 2 else 3
                return struct.pack("!iiB", int(val[0]), int(val[1]), units)
            return struct.pack("!iiB", int(val), int(val), 3)
        elif isinstance(val, str):
            return val.encode("utf-8")
        elif isinstance(val, bytes):
            return val
        return str(val).encode("utf-8")

    @classmethod
    def decode(cls, data: bytes) -> "IPPMessage":
        """Decode binary IPP message."""
        if len(data) < 8:
            raise ValueError(f"IPP message too short ({len(data)} bytes)")

        major, minor, op_status, req_id = struct.unpack("!BBHI", data[:8])
        msg = cls(version=(major, minor), operation_or_status=op_status, request_id=req_id)

        idx = 8
        current_group: Optional[List[IPPAttribute]] = None
        last_attr_name = ""

        while idx < len(data):
            tag = data[idx]
            idx += 1

            if tag == TAG_END_OF_ATTRIBUTES:
                msg.data = data[idx:]
                break

            if tag == TAG_OPERATION_ATTRIBUTES:
                current_group = msg.operation_attributes
                continue
            elif tag == TAG_JOB_ATTRIBUTES:
                current_group = msg.job_attributes
                continue
            elif tag == TAG_PRINTER_ATTRIBUTES:
                current_group = msg.printer_attributes
                continue
            elif tag == TAG_UNSUPPORTED:
                current_group = msg.unsupported_attributes
                continue

            if idx + 2 > len(data):
                break
            name_len = struct.unpack("!H", data[idx:idx + 2])[0]
            idx += 2
            if name_len > 0:
                name = data[idx:idx + name_len].decode("utf-8", errors="replace")
                last_attr_name = name
                idx += name_len
            else:
                name = last_attr_name

            if idx + 2 > len(data):
                break
            val_len = struct.unpack("!H", data[idx:idx + 2])[0]
            idx += 2
            raw_val = data[idx:idx + val_len]
            idx += val_len

            parsed_val = cls._decode_value(tag, raw_val)
            if current_group is not None:
                current_group.append(IPPAttribute(tag, name, parsed_val))

        return msg

    @staticmethod
    def _decode_value(tag: int, raw: bytes) -> Any:
        if tag in (TAG_INTEGER, TAG_ENUM):
            if len(raw) == 4:
                return struct.unpack("!i", raw)[0]
        elif tag == TAG_BOOLEAN:
            return raw[0] != 0 if raw else False
        elif tag == TAG_RESOLUTION and len(raw) == 9:
            x, y, u = struct.unpack("!iiB", raw)
            return (x, y, "dpi" if u == 3 else "dpcm")
        return raw.decode("utf-8", errors="replace")


class IPPClient:
    """Client for performing IPP operations directly against printer endpoints."""

    def __init__(self, printer_uri: str, timeout_sec: float = 600.0, verify_tls: bool = False):
        self.raw_printer_uri = printer_uri
        self.timeout_sec = timeout_sec  # 600 seconds (10 minutes) for photographic prints
        self.verify_tls = verify_tls
        self.cups_queue = self._detect_cups_queue(printer_uri)

        # Sanitize URI
        self.printer_uri, self.http_url = self._sanitize_uri(printer_uri)

    def _detect_cups_queue(self, uri: str) -> Optional[str]:
        """Detect local CUPS queue name for Canon G600/G640."""
        if "Canon_G600" in uri or "G600" in uri or "G640" in uri:
            return "Canon_G600_series"
        try:
            out = subprocess.check_output(["lpstat", "-p"], text=True)
            for line in out.splitlines():
                m = re.match(r"^printer\s+([^\s]+)", line)
                if m:
                    q = m.group(1)
                    if "G60" in q or "G64" in q or "Canon" in q:
                        return q
        except Exception:
            pass
        return "Canon_G600_series"

    @staticmethod
    def _sanitize_uri(uri: str) -> Tuple[str, str]:
        """
        Ensure URI contains no spaces or invalid mDNS characters.
        Returns (clean_ipp_uri, clean_http_url).
        """
        raw = uri.strip()

        is_tls = raw.startswith("ipps://") or raw.startswith("https://") or "_ipps" in raw
        scheme = "ipps" if is_tls else "ipp"
        http_scheme = "https" if is_tls else "http"

        host = "192.168.0.41"
        port = 631
        path = "ipp/print"

        ip_match = re.search(r"\b(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b", raw)
        if ip_match:
            host = ip_match.group(1)
            port_match = re.search(r":(\d+)", raw)
            if port_match:
                port = int(port_match.group(1))
        elif "cA5AB8400000" in raw:
            host = "cA5AB8400000.local"
        elif "G600" in raw or "G640" in raw or "canon" in raw.lower():
            host = "192.168.0.41"
        else:
            parsed = urllib.parse.urlparse(raw)
            if parsed.hostname:
                host = parsed.hostname
                port = parsed.port or 631
                path = parsed.path.lstrip("/") or "ipp/print"

        host = host.replace(" ", "").replace("%20", "")
        clean_ipp = f"{scheme}://{host}:{port}/{path}"
        clean_http = f"{http_scheme}://{host}:{port}/{path}"
        return clean_ipp, clean_http

    def _send_ipp_request(self, msg: IPPMessage) -> IPPMessage:
        """Send encoded IPP message over HTTP/HTTPS POST and return parsed response."""
        body = msg.encode()
        headers = {
            "Content-Type": "application/ipp",
            "User-Agent": "g640RIP/1.0 (macOS)",
            "Accept": "application/ipp",
        }
        req = urllib.request.Request(self.http_url, data=body, headers=headers, method="POST")

        context = ssl.create_default_context()
        if not self.verify_tls:
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE

        # High timeout (10 min) to allow long photo prints without socket dropping
        with urllib.request.urlopen(req, timeout=self.timeout_sec, context=context) as response:
            resp_data = response.read()
            return IPPMessage.decode(resp_data)

    def print_job(
        self,
        raster_data: bytes,
        document_format: str = "image/urf",
        job_name: str = "g640RIP-Job",
        media: Optional[str] = "iso_a4_210x297mm",
        media_type: Optional[str] = "com.canon.mtluster",
        print_quality: int = PRINT_QUALITY_HIGH,
        copies: int = 1,
        backend: str = "cups_raw",  # "cups_raw" (recommended) or "direct_ipp"
    ) -> Dict[str, Any]:
        """
        Send raw Print-Job operation directly with raster stream (image/urf).
        Completely bypasses macOS ColorSync and CUPS PPD filters.

        Using 'cups_raw' sends through macOS CUPS spooler with '-o raw', which:
        - NEVER times out while printing long 10-minute photo jobs.
        - Handles hardware printer backpressure and flow control.
        - Completely bypasses ColorSync and PPD filters.
        """
        # Option A: CUPS Raw Queue (Recommended for long photo prints)
        if backend in ("cups_raw", "auto") and self.cups_queue:
            try:
                with tempfile.NamedTemporaryFile(suffix=".urf", delete=False) as tmp:
                    tmp.write(raster_data)
                    tmp_path = tmp.name

                cmd = ["lp", "-d", self.cups_queue, "-o", "raw", "-t", job_name]
                if media:
                    cups_media = "4x6" if any(x in media.lower() for x in ("4x6", "10x15", "small-photo")) else ("A4" if "a4" in media.lower() else media)
                    cmd.extend(["-o", f"media={cups_media}"])
                    cmd.extend(["-o", f"PageSize={cups_media}"])
                if media_type:
                    cmd.extend(["-o", f"MediaType={media_type}"])
                cmd.append(tmp_path)

                out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
                os.remove(tmp_path)
                return {
                    "status": "OK",
                    "backend": f"CUPS-Raw ({self.cups_queue})",
                    "output": out.strip(),
                    "note": "Delivered via macOS Background Spooler (Raw URF, ColorSync Bypassed, Zero Timeout Risk)",
                }
            except Exception as cups_err:
                if backend == "cups_raw":
                    raise RuntimeError(f"CUPS Raw printing failed: {cups_err}")

        # Option B: Direct IPP socket transmission
        try:
            msg = IPPMessage(version=IPP_VERSION_2_0, operation_or_status=IPP_OP_PRINT_JOB)
            msg.add_operation_attr(TAG_CHARSET, "attributes-charset", "utf-8")
            msg.add_operation_attr(TAG_NATURAL_LANGUAGE, "attributes-natural-language", "en-us")
            msg.add_operation_attr(TAG_URI, "printer-uri", self.printer_uri)
            msg.add_operation_attr(TAG_NAME_WITHOUT_LANGUAGE, "job-name", job_name)
            msg.add_operation_attr(TAG_MIME_MEDIA_TYPE, "document-format", document_format)

            if copies > 1:
                msg.add_job_attr(TAG_INTEGER, "copies", copies)
            if media:
                msg.add_job_attr(TAG_KEYWORD, "media", media)
            if media_type:
                msg.add_job_attr(TAG_KEYWORD, "media-type", media_type)
            if print_quality:
                msg.add_job_attr(TAG_ENUM, "print-quality", print_quality)

            msg.data = raster_data

            resp = self._send_ipp_request(msg)
            if resp.operation_or_status in (STATUS_OK, 0x0001):
                job_info = {"status": "OK", "backend": "Direct-IPP", "status_code": resp.operation_or_status}
                for attr in resp.job_attributes:
                    job_info[attr.name] = attr.value
                return job_info
            else:
                raise RuntimeError(f"Direct IPP failed with status 0x{resp.operation_or_status:04x}")
        except Exception as direct_err:
            # Fallback to CUPS raw queue if direct socket fails
            if self.cups_queue:
                try:
                    with tempfile.NamedTemporaryFile(suffix=".urf", delete=False) as tmp:
                        tmp.write(raster_data)
                        tmp_path = tmp.name

                    cmd = ["lp", "-d", self.cups_queue, "-o", "raw", "-t", job_name]
                    if media:
                        cups_media = "4x6" if any(x in media.lower() for x in ("4x6", "10x15", "small-photo")) else ("A4" if "a4" in media.lower() else media)
                        cmd.extend(["-o", f"media={cups_media}"])
                        cmd.extend(["-o", f"PageSize={cups_media}"])
                    if media_type:
                        cmd.extend(["-o", f"MediaType={media_type}"])
                    cmd.append(tmp_path)
                    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
                    os.remove(tmp_path)
                    return {
                        "status": "OK",
                        "backend": f"CUPS-Raw-Fallback ({self.cups_queue})",
                        "output": out.strip(),
                        "note": "Delivered via CUPS Raw Spooler after direct IPP timeout (ColorSync Bypassed)",
                    }
                except Exception as cups_err:
                    raise RuntimeError(f"Direct IPP timed out ({direct_err}) and CUPS fallback failed ({cups_err})")

            raise RuntimeError(f"Direct IPP print failed: {direct_err}")

    def cancel_job(self, job_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Cancel print job via IPP and macOS CUPS queue.
        If job_id is None, cancels all active jobs on the queue.
        """
        details = []

        if job_id:
            try:
                msg = IPPMessage(version=IPP_VERSION_2_0, operation_or_status=IPP_OP_CANCEL_JOB)
                msg.add_operation_attr(TAG_CHARSET, "attributes-charset", "utf-8")
                msg.add_operation_attr(TAG_NATURAL_LANGUAGE, "attributes-natural-language", "en-us")
                msg.add_operation_attr(TAG_URI, "printer-uri", self.printer_uri)
                msg.add_operation_attr(TAG_INTEGER, "job-id", job_id)
                resp = self._send_ipp_request(msg)
                details.append(f"IPP cancel status: 0x{resp.operation_or_status:04x}")
            except Exception as e:
                details.append(f"IPP cancel note: {e}")

        target_queue = self.cups_queue or "Canon_G600_series"
        try:
            if job_id:
                cmd = ["cancel", f"{target_queue}-{job_id}"]
            else:
                cmd = ["cancel", "-a", target_queue]
            out = subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)
            details.append(f"CUPS cancel ({target_queue}): {out.strip() or 'Purged'}")
        except Exception as e:
            try:
                subprocess.run(["cancel", "-a"], check=False)
                details.append("Purged all local print queues")
            except Exception:
                details.append(f"CUPS cancel error: {e}")

        return {"status": "cancelled", "details": details}
