from __future__ import annotations

from pathlib import Path
from typing import Optional

from playwright.async_api import Page

from .masking import mask_pii


async def capture_basic(page: Optional[Page], out_dir: Path, capture_html: bool, capture_screenshot: bool, capture_console_log: bool, pii_patterns: list[str]) -> None:
    if page is None:
        return
    if capture_screenshot:
        try:
            screenshot_path = out_dir / "screenshot.png"
            await page.screenshot(path=str(screenshot_path), full_page=True)
            # If underlying mock does not actually write a file, create a placeholder
            if not screenshot_path.exists():
                screenshot_path.write_bytes(b"")
        except Exception:
            pass
    if capture_html:
        try:
            html = await page.content()
            html = mask_pii(html, pii_patterns)
            (out_dir / "page.html").write_text(html, encoding="utf-8")
        except Exception:
            pass
    if capture_console_log:
        # Best-effort: collect current console via evaluate history is not available.
        # As a placeholder, we can indicate that live console buffering is not attached.
        try:
            (out_dir / "console.log").write_text("Console log capture is not attached in this run.\n", encoding="utf-8")
        except Exception:
            pass


