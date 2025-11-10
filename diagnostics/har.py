from __future__ import annotations

from pathlib import Path
from playwright.async_api import BrowserContext


async def capture_har(context: BrowserContext, out_dir: Path) -> None:
    # Playwright HAR usually requires context creation with record_har_path.
    # Here we provide a placeholder to not fail the run.
    try:
        # No standard API to export HAR post-factum; document requirement.
        (out_dir / "har.NOT_AVAILABLE.txt").write_text(
            "HAR export requires context created with record_har_path. Not available in this run.\n",
            encoding="utf-8",
        )
    except Exception:
        pass


