"""
Pydantic schemas for structured LLM responses using Function Calling.
"""
from typing import Annotated, Optional, List

from pydantic import BaseModel, Field, conint


class SkillsMatch(BaseModel):
    """
    Detailed information about matched and missing skills.
    """
    total: int = Field(..., ge=0, description="Total number of skills")
    matched_count: int = Field(..., ge=0, description="Number of matched skills")
    missing_count: int = Field(..., ge=0, description="Number of missing skills")
    matched: List[str] = Field(default_factory=list, description="List of matched skills (normalized, unique, alphabetically sorted)")
    missing: List[str] = Field(default_factory=list, description="List of missing skills (normalized, unique, alphabetically sorted)")


class Experience(BaseModel):
    """
    Experience and seniority information.
    """
    required_years: Optional[int] = Field(None, ge=0, description="Required years of experience")
    candidate_years: Optional[int] = Field(None, ge=0, description="Candidate's years of experience")
    required_seniority: Optional[str] = Field(
        None,
        description="Required seniority level: intern|junior|middle|senior|lead|principal|staff|architect"
    )
    candidate_seniority: Optional[str] = Field(
        None,
        description="Candidate's seniority level: intern|junior|middle|senior|lead|principal|staff|architect"
    )


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
    required: SkillsMatch = Field(..., description="Required skills match details")
    optional: SkillsMatch = Field(..., description="Optional skills match details")
    experience: Experience = Field(..., description="Experience and seniority details")
