"""Minimal cgi module compatibility for Python 3.13+.

Only implements parse_header, which is required by the vendored
Alibaba Cloud requests fork bundled with the NLS SDK.
"""
from __future__ import annotations

from email.message import Message
from email.parser import HeaderParser
from typing import Dict, Tuple

__all__ = ["parse_header"]


def parse_header(line: str) -> Tuple[str, Dict[str, str]]:
    """Parse a Content-Type style header.

    Mirrors the legacy cgi.parse_header behavior well enough for requests,
    including returning a lower-cased parameter dict.
    """
    if not line:
        return "", {}

    parser = HeaderParser()
    msg: Message = parser.parsestr(f"Content-Type: {line}\n", headersonly=True)
    value = msg.get("Content-Type", "")
    params = msg.get_params(header="Content-Type") or []
    # First entry is the main content-type pair. Subsequent entries are params.
    pdict: Dict[str, str] = {}
    for key, val in params[1:]:
        if key:
            pdict[key.lower()] = val
    return value, pdict
