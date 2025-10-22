import logging
from unittest.mock import MagicMock, patch

from llm.cover_letter_generator import generate_cover_letter
from llm.structured_schemas import LetterParts


@patch("llm.cover_letter_generator.save_cover_letter")
@patch(
    "llm.cover_letter_generator.read_resume_text",
    return_value="This is my resume.",
)
@patch(
    "llm.cover_letter_generator.get_vacancy_by_id",
    return_value={
        "id": "e2e-cl-001",
        "title": "Test Engineer",
        "description": "A job for testing.",
    },
)
@patch("llm.cover_letter_generator.get_llm_client")
def test_cover_letter_generation_end_to_end(
    mock_get_llm_client: MagicMock,
    mock_get_vacancy: MagicMock,
    mock_read_resume: MagicMock,
    mock_save_cover_letter: MagicMock,
    tmp_path,
    caplog,
    app_config,
):
    """
    End-to-end test for generating and saving a cover letter.

    This test verifies the complete flow from generating a cover letter using a
    mocked LLM to saving it to a file, ensuring all components are integrated correctly.
    """
    vacancy_id = "e2e-cl-001"
    expected_greeting = "Dear Test Manager,"
    # Each paragraph must have >= 40 words according to LetterParts validation
    expected_paragraphs = [
        " ".join(["This is the first paragraph with enough words to meet validation requirements."] * 10),
        " ".join(["This is the second paragraph with enough words to meet validation requirements."] * 10),
        " ".join(["This is the third paragraph with enough words to meet validation requirements."] * 10),
    ]
    expected_closing = "Yours Faithfully,"
    expected_signature = "Testy Tester"

    # Mock the LLM client to return a predictable structured response
    mock_llm = MagicMock()
    mock_get_llm_client.return_value = mock_llm

    mock_parts = LetterParts(
        greeting=expected_greeting,
        paragraphs=expected_paragraphs,
        closing=expected_closing,
        signature=expected_signature,
    )
    mock_llm.generate_structured_response.return_value = mock_parts

    # 1. Generation Phase
    with caplog.at_level(logging.INFO):
        generated_letter = generate_cover_letter(vacancy_id, app_config)

    # Verify generation
    assert expected_greeting in generated_letter
    assert expected_paragraphs[0] in generated_letter
    assert expected_closing in generated_letter
    assert expected_signature in generated_letter
    assert "cover letter for the vacancy has been generated" in caplog.text

    # Verify that the correct methods were called
    mock_get_vacancy.assert_called_once_with(vacancy_id, app_config.session.db_conn)
    mock_read_resume.assert_called_once_with(app_config)
    mock_llm.generate_structured_response.assert_called_once()
