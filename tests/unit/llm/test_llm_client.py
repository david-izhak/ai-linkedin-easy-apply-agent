import logging
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage

from llm.exceptions import LLMGenerationError
from llm.llm_client import LLMClient


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Fixture to mock LLM settings."""
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-4-turbo")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.5")
    monkeypatch.setenv("LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("LLM_TIMEOUT", "60")


@patch("llm.llm_client.ChatOpenAI")
def test_llm_client_initialization_openai(mock_chat_openai, app_config):
    """Test that ChatOpenAI is used when provider is 'openai'."""
    llm_config = app_config.llm.model_copy(update={"LLM_PROVIDER": "openai"})
    llm_client = LLMClient(llm_config)
    mock_chat_openai.assert_called_once()
    assert llm_client.provider == "openai"


@patch("llm.llm_client.ChatOllama")
def test_llm_client_initialization_ollama(mock_ollama, app_config):
    """Test that ChatOllama is used when provider is 'ollama'."""
    llm_config = app_config.llm.model_copy(update={"LLM_PROVIDER": "ollama"})
    llm_client = LLMClient(llm_config)
    mock_ollama.assert_called_once()
    assert llm_client.provider == "ollama"


@patch("llm.llm_client.ChatAnthropic")
def test_llm_client_initialization_anthropic(mock_anthropic, app_config):
    """Test that ChatAnthropic is used when provider is 'anthropic'."""
    llm_config = app_config.llm.model_copy(update={"LLM_PROVIDER": "anthropic"})
    llm_client = LLMClient(llm_config)
    mock_anthropic.assert_called_once()
    assert llm_client.provider == "anthropic"


def test_llm_client_initialization_invalid_provider(app_config):
    """Test that a ValueError is raised for an invalid provider."""
    llm_config = app_config.llm.model_copy(update={"LLM_PROVIDER": "invalid_provider"})
    with pytest.raises(ValueError, match="Unsupported LLM provider: invalid_provider"):
        LLMClient(llm_config)


@patch("llm.llm_client.ChatOpenAI")
def test_generate_response_with_content_attribute(mock_chat_openai, app_config):
    """Test handling of response object with a .content attribute."""
    llm_config = app_config.llm.model_copy(update={"LLM_PROVIDER": "openai"})
    mock_client_instance = mock_chat_openai.return_value
    mock_client_instance.invoke.return_value = AIMessage(content="Test response")

    llm_client = LLMClient(llm_config)
    result = llm_client.generate_response("prompt")
    assert result == "Test response"


@patch("llm.llm_client.ChatOpenAI")
def test_generate_response_with_string_return(mock_chat_openai, app_config):
    """Test handling of a direct string response."""
    llm_config = app_config.llm.model_copy(update={"LLM_PROVIDER": "openai"})
    mock_client_instance = mock_chat_openai.return_value
    mock_client_instance.invoke.return_value = "Plain string response"

    llm_client = LLMClient(llm_config)
    result = llm_client.generate_response("prompt")
    assert result == "Plain string response"


@patch("llm.llm_client.ChatOpenAI")
def test_generate_response_logs_and_raises_error_on_exception(
    mock_chat_openai, app_config, caplog
):
    """Test that an exception during generation is logged and re-raised."""
    llm_config = app_config.llm.model_copy(update={"LLM_PROVIDER": "openai"})
    mock_client_instance = mock_chat_openai.return_value
    mock_client_instance.invoke.side_effect = Exception("API Error")

    llm_client = LLMClient(llm_config)
    with caplog.at_level(logging.ERROR):
        with pytest.raises(LLMGenerationError):
            llm_client.generate_response("prompt")

    assert "Failed to generate response from LLM" in caplog.text
