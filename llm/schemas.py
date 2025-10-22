"""
Pydantic schemas for structured LLM responses using Function Calling.
"""
from typing import Annotated

from pydantic import BaseModel, Field, conint


class MatchResult(BaseModel):
    """
    Structured response for vacancy match calculation.
    Represents the match percentage and analysis of candidate skills vs job requirements.
    """

    match_percentage: Annotated[int, Field(ge=0, le=100, description="Match percentage from 0 to 100")]
    analysis: str = Field(
        ...,
        description="Brief analysis (max 1000 characters recommended)",
        max_length=1000,
    )
