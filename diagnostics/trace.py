from __future__ import annotations

from pathlib import Path
from playwright.async_api import BrowserContext


async def capture_trace(context: BrowserContext, out_dir: Path) -> None:
    try:
        await context.tracing.start(screenshots=True, snapshots=True, sources=False)
    except Exception:
        # tracing may already be started or unsupported
        pass
    try:
        await context.tracing.stop(path=str(out_dir / "trace.zip"))
    except Exception:
        # If tracing was not started or cannot stop, ignore
        pass


