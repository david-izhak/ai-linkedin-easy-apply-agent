"""
Pydantic models for Candidate Profile.

Based on technical specification section 4.1.
"""

from typing import Dict, Optional
from pydantic import BaseModel, Field, field_validator, HttpUrl


class YearsExperience(BaseModel):
    """Years of experience in various technologies."""
    python: Optional[int] = Field(default=0, ge=0, le=50)
    java: Optional[int] = Field(default=0, ge=0, le=50)
    spark: Optional[int] = Field(default=0, ge=0, le=50)
    kubernetes: Optional[int] = Field(default=0, ge=0, le=50)
    aws: Optional[int] = Field(default=0, ge=0, le=50)
    gcp: Optional[int] = Field(default=0, ge=0, le=50)
    azure: Optional[int] = Field(default=0, ge=0, le=50)
    
    # Allow additional technologies dynamically
    class Config:
        extra = "allow"


class SalaryExpectation(BaseModel):
    """Salary expectations in different currencies."""
    monthly_net_nis: Optional[int] = Field(default=None, ge=0)
    monthly_net_usd: Optional[int] = Field(default=None, ge=0)
    monthly_net_eur: Optional[int] = Field(default=None, ge=0)
    
    class Config:
        extra = "allow"


class WorkAuthorization(BaseModel):
    """Work authorization status for different regions."""
    IL: Optional[str] = Field(default=None)  # "yes", "need_visa", "no"
    EU: Optional[str] = Field(default=None)
    US: Optional[str] = Field(default=None)
    
    @field_validator("IL", "EU", "US")
    @classmethod
    def validate_authorization(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v_lower = v.lower()
        allowed = {"yes", "need_visa", "no", "да", "нужна виза", "нет"}
        if v_lower not in allowed:
            raise ValueError(f"Authorization status must be one of {allowed}")
        return v_lower
    
    class Config:
        extra = "allow"


class Links(BaseModel):
    """Professional links and portfolio."""
    github: Optional[HttpUrl] = None
    linkedin: Optional[HttpUrl] = None
    portfolio: Optional[HttpUrl] = None
    
    class Config:
        extra = "allow"


class CandidateProfile(BaseModel):
    """Complete candidate profile for form filling."""
    
    # Strictly typed nested structures
    years_experience: Optional[YearsExperience] = Field(default_factory=YearsExperience)
    salary_expectation: Optional[SalaryExpectation] = Field(default_factory=SalaryExpectation)
    work_authorization: Optional[WorkAuthorization] = Field(default_factory=WorkAuthorization)
    links: Optional[Links] = Field(default_factory=Links)
    
    # Common simple fields (for IDE autocomplete and documentation)
    notice_period_days: Optional[int] = Field(default=0, ge=0, le=365)
    preferred_location: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None, max_length=20)
    short_bio_en: Optional[str] = Field(default=None, max_length=500)
    short_bio_ru: Optional[str] = Field(default=None, max_length=500)
    
    class Config:
        extra = "allow"  # Allow any additional fields from JSON without schema modification
    
    def to_json_summary(self) -> Dict:
        """
        Convert profile to a JSON-safe dict for LLM context.

        Returns the full profile (excluding None values) so downstream
        consumers receive complete information when constructing prompts.
        """
        return self.model_dump(exclude_none=True)
    
    def get_nested_value(self, key_path: str) -> any:
        """
        Get a nested value from the profile using dot notation.
        Example: "years_experience.python" -> 7
        """
        parts = key_path.split(".")
        current = self.model_dump()
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

