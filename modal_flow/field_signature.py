"""
Models for field signatures used in rule matching.

Based on technical specification section 4.3.
"""

import hashlib
from dataclasses import dataclass
from typing import Optional, List


def options_fingerprint(options: List[str]) -> str:
    """
    Generate a SHA1 fingerprint of normalized options.
    
    Used to uniquely identify a set of options for rule matching.
    """
    if not options:
        return ""
    
    # Normalize each option: lowercase, trim, collapse whitespace
    normalized = [" ".join(o.lower().split()) for o in options]
    # Sort for consistent ordering
    blob = "|".join(sorted(normalized))
    # Generate SHA1 hash
    hash_obj = hashlib.sha1(blob.encode("utf-8"))
    return "sha1:" + hash_obj.hexdigest()


@dataclass
class FieldSignature:
    """
    Signature of a form field used for rule matching.
    
    Attributes:
        field_type: Type of field (radio, checkbox, select, text, number, etc.)
        q_norm: Normalized question text
        opts_fp: Options fingerprint (SHA1 hash) if field has options
        site: Site/domain context (e.g., "linkedin.com" or "*")
        form_kind: Type of form (e.g., "job_apply")
        locale: Language locale (e.g., "en", "ru")
    """
    field_type: str
    q_norm: str
    opts_fp: Optional[str]
    site: str
    form_kind: str
    locale: str
    
    def __post_init__(self):
        """Validate field type."""
        allowed_types = {"radio", "checkbox", "select", "combobox", "text", "number", "multiselect"}
        if self.field_type not in allowed_types:
            raise ValueError(f"field_type must be one of {allowed_types}")



