import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from diagnostics import DiagnosticOptions, DiagnosticContext, capture_on_failure


@pytest.mark.asyncio
async def test_capture_basic_artifacts(tmp_path: Path):
    context = AsyncMock()
    page = AsyncMock()
    page.content = AsyncMock(return_value="<html><body>Email: test@example.com</body></html>")
    page.screenshot = AsyncMock()

    options = DiagnosticOptions(
        enable_on_failure=True,
        capture_screenshot=True,
        capture_html=True,
        capture_console_log=True,
        capture_har=False,
        capture_trace=False,
        output_dir=tmp_path,
        max_artifacts_per_run=10,
        pii_mask_patterns=[r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"],
        phases_enabled=["enrichment"],
    )
    dctx = DiagnosticContext(
        phase="enrichment",
        job_id=123,
        link="https://example.com",
        error=RuntimeError("boom"),
        tracker_state={"x": 1},
    )

    out_dir = await capture_on_failure(context, page, options, dctx)
    assert out_dir is not None
    assert (out_dir / "page.html").exists()
    assert (out_dir / "screenshot.png").exists()

    html = (out_dir / "page.html").read_text(encoding="utf-8")
    assert "***" in html  # masked


@pytest.mark.asyncio
async def test_capture_respects_phase_disable(tmp_path: Path):
    context = AsyncMock()
    page = AsyncMock()
    options = DiagnosticOptions(
        enable_on_failure=True,
        output_dir=tmp_path,
        phases_enabled=["processing"],  # enrichment is disabled
    )
    dctx = DiagnosticContext(phase="enrichment", job_id=None, link=None, error=None, tracker_state={})

    out_dir = await capture_on_failure(context, page, options, dctx)
    assert out_dir is None


@pytest.mark.asyncio
async def test_capture_trace_and_har(tmp_path: Path):
    context = AsyncMock()
    page = AsyncMock()
    options = DiagnosticOptions(
        enable_on_failure=True,
        capture_trace=True,
        capture_har=True,
        output_dir=tmp_path,
        phases_enabled=["discovery"],
    )
    dctx = DiagnosticContext(phase="discovery", job_id=1, link=None, error=None, tracker_state={})

    out_dir = await capture_on_failure(context, page, options, dctx)
    assert out_dir is not None
    # trace.zip may or may not be present depending on tracing support, but HAR placeholder should exist
    assert (out_dir / "har.NOT_AVAILABLE.txt").exists()


