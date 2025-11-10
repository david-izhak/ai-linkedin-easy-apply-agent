from __future__ import annotations

from pathlib import Path
from typing import Optional

from playwright.async_api import BrowserContext, Page

from .types import DiagnosticOptions, DiagnosticContext
from .naming import build_artifact_dir
from .storage import ensure_dir, enforce_limit
from .basic import capture_basic
from .trace import capture_trace
from .har import capture_har


async def capture_on_failure(
    context: BrowserContext,
    page: Optional[Page],
    options: DiagnosticOptions,
    dctx: DiagnosticContext,
) -> Optional[Path]:
    if not options.enable_on_failure:
        return None
    if dctx.phase not in options.phases_enabled:
        return None

    error_key = type(dctx.error).__name__ if dctx.error else "UnknownError"
    base = Path(options.output_dir)
    out_dir = build_artifact_dir(base, dctx.phase, dctx.job_id, error_key)
    ensure_dir(out_dir)

    # Enforce total artifacts limit per run (by top-level base dir)
    enforce_limit(base / dctx.phase, options.max_artifacts_per_run)

    # Basic artifacts
    await capture_basic(
        page,
        out_dir,
        options.capture_html,
        options.capture_screenshot,
        options.capture_console_log,
        options.pii_mask_patterns,
    )

    # HAR and Trace (best-effort)
    if options.capture_har:
        await capture_har(context, out_dir)
    if options.capture_trace:
        await capture_trace(context, out_dir)

    return out_dir


