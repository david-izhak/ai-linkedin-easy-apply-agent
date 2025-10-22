class LLMGenerationError(Exception):
    """Exception for errors when generating a response from LLM."""

    def __init__(
        self,
        message: str | None = None,
        prompt: str | None = None,
        provider: str | None = None,
        model: str | None = None,
    ):
        # Allow a simplified call with one message (as in tests),
        # and maintain compatibility with detailed context via named arguments.
        base_message = message if message is not None else "LLM generation error"
        details = []
        if provider is not None:
            details.append(f"Provider: {provider}")
        if model is not None:
            details.append(f"Model: {model}")
        if prompt is not None:
            details.append(f"Prompt: {prompt}.")
        full_message = " ".join([base_message] + details) if details else base_message
        self.message = full_message
        super().__init__(self.message)


class ResumeReadError(Exception):
    """Exception raised when reading resume file fails."""

    def __init__(self, path: str, message: str | None = None):
        # We allow you to specify the message text explicitly (to comply with tests),
        # Otherwise, we use the general default message.
        self.message = (
            message if message is not None else f"Failed to read resume file at: {path}"
        )
        super().__init__(self.message)


class VacancyNotFoundError(Exception):
    """Exception raised when a vacancy is not found in the database."""

    def __init__(self, vacancy_id: int):
        self.message = f"Vacancy with ID {vacancy_id} was not found in the database"
        super().__init__(self.message)


class CoverLetterGenerationError(Exception):
    """Exception thrown when there is a general error generating the cover letter."""

    def __init__(self, vacancy_id: int, resume_path: str):
        self.message = f"Error generating cover letter for job posting {vacancy_id}"
        super().__init__(self.message, f"Path to the resume file: {resume_path}")


class CoverLetterSaveError(Exception):
    """Exception raised when saving cover letter fails."""

    def __init__(self, vacancy_id: int, cover_letter_text: str, output_dir: str):
        self.message = "Error saving cover letter."
        super().__init__(
            self.message,
            f"Job posting ID: {vacancy_id}",
            f"Cover letter text: {cover_letter_text}",
            f"Directory for saving files: {output_dir}",
        )
