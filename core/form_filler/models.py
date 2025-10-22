from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class JobApplicationContext:
    """Context information about current job application."""

    job_id: int
    job_url: str
    job_title: str
    should_submit: bool
    cover_letter_path: Optional[Path] = None
    job_description: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_job_payload(self) -> Dict[str, Any]:
        """Serialize context for logging/LLM."""
        payload = {
            "job_id": self.job_id,
            "job_url": self.job_url,
            "job_title": self.job_title,
        }
        if self.job_description:
            payload["job_description"] = self.job_description
        payload.update(self.metadata or {})
        return payload


@dataclass
class FillResult:
    """Result of filling a job application form."""

    completed: bool
    submitted: bool
    validation_errors: List[str]
    mode: str


class FormFillError(Exception):
    """Raised when a form filler fails to complete the process."""

    def __init__(self, message: str, validation_errors: Optional[List[str]] = None):
        super().__init__(message)
        self.validation_errors = validation_errors or []
