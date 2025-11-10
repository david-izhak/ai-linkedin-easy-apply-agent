from __future__ import annotations

import re
from typing import Iterable


DEFAULT_PATTERNS = [
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
]


def mask_pii(text: str, patterns: Iterable[str]) -> str:
    patterns_list = list(patterns) if patterns else []
    # Always include default patterns such as email
    all_patterns = DEFAULT_PATTERNS + patterns_list
    masked = text
    for pat in all_patterns:
        try:
            masked = re.sub(pat, "***", masked, flags=re.IGNORECASE)
        except re.error:
            # Ignore invalid regex to avoid breaking diagnostics
            continue
    return masked


