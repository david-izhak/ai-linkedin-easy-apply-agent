import logging
from typing import TypeVar, Type
from langchain_openai import ChatOpenAI
from langchain_community.chat_models import ChatOllama
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel, SecretStr

from config import LLMSettings
from llm.exceptions import LLMGenerationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self, llm_config: LLMSettings):
        self.provider = llm_config.LLM_PROVIDER
        self.model = llm_config.LLM_MODEL
        self.api_key = llm_config.LLM_API_KEY
        self.timeout = llm_config.LLM_TIMEOUT
        self.max_retries = llm_config.LLM_MAX_RETRIES
        self.base_url = llm_config.LLM_BASE_URL
        self.temperature = llm_config.LLM_TEMPERATURE

        logger.info(
            f"LLMClient initialized with provider={self.provider}, model={self.model}, base_url={self.base_url}, temperature={self.temperature}, timeout={self.timeout}, max_retries={self.max_retries}"
        )

        # Initialize LLM client depending on provider
        if self.provider == "openai":
            self.client = ChatOpenAI(
                model=self.model,
                base_url=self.base_url,
                api_key=SecretStr(self.api_key),
                timeout=self.timeout,
                max_retries=self.max_retries,
                temperature=self.temperature,
            )
        elif self.provider == "ollama":
            # The Ollama client does not have built-in retries, we add them using .with_retry()
            llm = ChatOllama(
                model=self.model, base_url=self.base_url, temperature=self.temperature
            )
            self.client = llm.with_retry(
                stop_after_attempt=self.max_retries,
                wait_exponential_jitter=True,  # Uses exponential backoff like other clients
            )
        elif self.provider == "anthropic":
            self.client = ChatAnthropic(
                model_name=self.model,
                api_key=SecretStr(self.api_key),
                timeout=self.timeout,
                max_retries=self.max_retries,
                temperature=self.temperature,
            )
        elif self.provider == "google":
            self.client = ChatGoogleGenerativeAI(
                model=self.model,
                google_api_key=SecretStr(self.api_key),
                timeout=self.timeout,
                max_retries=self.max_retries,
                temperature=self.temperature,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")

    def generate_response(self, prompt: str) -> str:
        """
        Generate LLM response based on prompt (legacy method for backward compatibility).
        For new code, prefer generate_structured_response().
        """
        try:
            logger.debug(f"Generating LLM response for prompt: {prompt[:100]}...")
            response = self.client.invoke(prompt)
            # Langchain clients return different types of responses.
            # AIMessage has .content, while older LLMs may return a string.
            if hasattr(response, "content"):
                content = response.content
            else:
                content = str(response)

            logger.debug(f"LLM raw response: {content}")
            return content
        except Exception as e:
            logger.error(
                f"Failed to generate response from LLM after {self.max_retries} attempts: {str(e)}"
            )
            raise LLMGenerationError(
                prompt=prompt, provider=self.provider, model=self.model
            ) from e

    def generate_structured_response(
        self, prompt: str, schema: Type[T], system_message: str | None = None
    ) -> T:
        """
        Generate structured LLM response using Function Calling / Tool Use.
        
        This method uses LangChain's with_structured_output() which internally
        uses function calling to ensure the model returns a strictly typed response
        matching the provided Pydantic schema.
        
        Args:
            prompt: The user prompt/question
            schema: Pydantic model class that defines the expected response structure
            system_message: Optional system message to guide the model behavior
            
        Returns:
            Instance of the provided schema type with validated data
            
        Raises:
            LLMGenerationError: If the LLM fails to generate a valid response
        """
        try:
            logger.debug(
                f"Generating structured LLM response for schema: {schema.__name__}"
            )
            
            # Create structured LLM with function calling
            # This forces the model to return data matching the schema
            structured_llm = self.client.with_structured_output(
                schema, method="function_calling"
            )
            
            # Prepare messages
            messages = []
            if system_message:
                messages.append(SystemMessage(content=system_message))
            messages.append(HumanMessage(content=prompt))
            
            # Invoke and get structured response
            result: T = structured_llm.invoke(messages)
            
            logger.debug(
                f"LLM structured response received: {result.model_dump_json(indent=2)}"
            )
            return result
            
        except Exception as e:
            # Try tolerant fallback to salvage usable data for downstream fixers
            logger.warning(
                f"Structured output failed ({type(e).__name__}: {e}). Trying tolerant fallback."
            )
            try:
                # Rebuild messages for a raw invoke
                messages = []
                if system_message:
                    messages.append(SystemMessage(content=system_message))
                messages.append(HumanMessage(content=prompt))

                raw = self.client.invoke(messages)
                content = getattr(raw, "content", None) or str(raw)

                # Extract first JSON object from the content
                import re
                import json
                match = re.search(r"\{[\s\S]*\}", content)
                if match:
                    data = json.loads(match.group(0))
                    logger.debug(f"Tolerant fallback parsed dict: {data}")
                    # Return dict; callers (delegates) will validate/repair
                    return data  # type: ignore[return-value]
                else:
                    logger.debug("Tolerant fallback: no JSON object found in content.")
                    raise ValueError("No JSON object found in fallback content.")
            except Exception as e2:
                logger.error(
                    f"Failed to generate structured response from LLM after fallback: {e2}"
                )
                raise LLMGenerationError(
                    prompt=prompt, provider=self.provider, model=self.model
                ) from e
