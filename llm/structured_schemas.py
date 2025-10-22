from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


# ===== 1) A rigid result scheme (no markdown) =====

BANNED_MD_TOKENS = ("```", "#", "*", "_", ">", "[", "]")


class LetterParts(BaseModel):
    """
    Represents the structured components of a cover letter.

    This Pydantic model ensures that the generated cover letter parts are
    free of Markdown formatting and meet certain length requirements.
    """
    greeting: str = Field(..., description="E.g.: 'Dear Hiring Manager,' without markdown")
    paragraphs: List[str] = Field(..., min_length=3, max_length=5, description="3–5 paragraphs, plain text")
    closing: str = Field(..., description="E.g.: 'Sincerely,'")
    signature: str = Field(..., description="Name and contacts, no markdown")
    ps: Optional[str] = Field(None, description="Optional P.S. no markdown")

    @field_validator("greeting", "closing", "signature", "ps", mode="before")
    @classmethod
    def forbid_md_simple(cls, v):
        """Checks for and rejects simple markdown tokens."""
        if v is None:
            return v
        if any(tok in v for tok in BANNED_MD_TOKENS):
            raise ValueError("Markdown is not allowed.")
        return v.strip()

    @field_validator("paragraphs")
    @classmethod
    def paragraphs_plain_and_sized(cls, paras: List[str]):
        """
        Validates that paragraphs are plain text and meet the length requirement.
        """
        for p in paras:
            if any(tok in p for tok in BANNED_MD_TOKENS):
                raise ValueError("Markdown is not allowed in paragraphs.")
            # light protection against ultra-short paragraphs
            if len(p.split()) < 40:
                raise ValueError("Each paragraph should be concise but substantial (>= 40 words).")
        return [p.strip() for p in paras]


def join_parts(lp: LetterParts) -> str:
    """
    Combines the structured parts of a cover letter into a single plain-text string.
    """
    chunks = [lp.greeting, ""]
    chunks += lp.paragraphs
    chunks += ["", lp.closing, lp.signature]
    if lp.ps:
        chunks += ["", f"P.S. {lp.ps}"]
    return "\n".join(chunks).strip()



