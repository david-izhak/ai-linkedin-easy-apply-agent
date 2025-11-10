from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional


def build_artifact_dir(base: Path, phase: str, job_id: Optional[int], error_key: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    jid = str(job_id) if job_id is not None else "nojob"
    return base / phase / f"{ts}_{jid}_{error_key}"


