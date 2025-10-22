from functools import lru_cache
from llm.llm_client import LLMClient
from config import LLMSettings


@lru_cache(maxsize=None)
def get_llm_client(llm_config: LLMSettings) -> LLMClient:
    """
    Returns a singleton instance of LLMClient using lru_cache.
    """
    return LLMClient(llm_config)
