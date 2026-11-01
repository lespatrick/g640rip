"""Transport and IPP communication modules for Canon G640."""

from .constants import CANON_MEDIA_TYPES, PAPER_SIZES, PRINT_QUALITY_DRAFT, PRINT_QUALITY_HIGH, PRINT_QUALITY_NORMAL
from .discovery import PrinterInfo, discover_canon_printers, probe_cups_for_canon, resolve_mdns_host_ipv4
from .ipp_client import IPPClient, IPPMessage

__all__ = [
    "PrinterInfo",
    "discover_canon_printers",
    "probe_cups_for_canon",
    "resolve_mdns_host_ipv4",
    "IPPClient",
    "IPPMessage",
    "CANON_MEDIA_TYPES",
    "PAPER_SIZES",
    "PRINT_QUALITY_DRAFT",
    "PRINT_QUALITY_NORMAL",
    "PRINT_QUALITY_HIGH",
]

