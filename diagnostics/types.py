from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class DiagnosticOptions:
    enable_on_failure: bool = False
    capture_screenshot: bool = True
    capture_html: bool = True
    capture_console_log: bool = True
    capture_har: bool = False
    capture_trace: bool = False
    output_dir: Path = Path("./logs/diagnostics")
    max_artifacts_per_run: int = 10
    pii_mask_patterns: list[str] = field(default_factory=list)
    phases_enabled: list[str] = field(default_factory=lambda: ["discovery", "enrichment", "processing"])


@dataclass
class DiagnosticContext:
    phase: str
    job_id: Optional[int]
    link: Optional[str]
    error: Optional[BaseException]
    tracker_state: Dict[str, int] = field(default_factory=dict)
    timestamp: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


