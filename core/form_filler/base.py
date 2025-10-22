import abc
from typing import Protocol

from playwright.async_api import Page

from config import AppConfig
from .models import JobApplicationContext, FillResult


class FormFiller(Protocol):
    """Protocol for form fillers."""

    async def fill(
        self,
        page: Page,
        app_config: AppConfig,
        job_context: JobApplicationContext,
    ) -> FillResult:
        ...


class AbstractFormFiller(abc.ABC):
    """Abstract base class implementing the FormFiller protocol."""

    @abc.abstractmethod
    async def fill(
        self,
        page: Page,
        app_config: AppConfig,
        job_context: JobApplicationContext,
    ) -> FillResult:
        """Fill the application form."""
        raise NotImplementedError
