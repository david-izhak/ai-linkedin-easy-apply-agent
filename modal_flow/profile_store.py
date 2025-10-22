"""
ProfileStore: Load and validate candidate profiles from JSON/YAML files.

Based on technical specification section 3.1.
"""

import json
import yaml
from pathlib import Path
from typing import Union

from modal_flow.profile_schema import CandidateProfile


class ProfileStore:
    """Loads and validates candidate profiles from storage."""
    
    def __init__(self, profile_path: Union[str, Path]):
        """
        Initialize ProfileStore with a path to profile file.
        
        Args:
            profile_path: Path to JSON or YAML file containing profile data
        """
        self.profile_path = Path(profile_path)
        if not self.profile_path.exists():
            raise FileNotFoundError(f"Profile file not found: {self.profile_path}")
    
    def load(self) -> CandidateProfile:
        """
        Load profile from file and validate with Pydantic.
        
        Returns:
            Validated CandidateProfile instance
            
        Raises:
            ValidationError: If profile data doesn't match schema
            FileNotFoundError: If file doesn't exist
        """
        suffix = self.profile_path.suffix.lower()
        
        if suffix == ".json":
            return self._load_from_json()
        elif suffix in (".yaml", ".yml"):
            return self._load_from_yaml()
        else:
            raise ValueError(f"Unsupported file format: {suffix}. Use .json or .yaml")
    
    def _load_from_json(self) -> CandidateProfile:
        """Load profile from JSON file."""
        with open(self.profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return CandidateProfile.model_validate(data)
    
    def _load_from_yaml(self) -> CandidateProfile:
        """Load profile from YAML file."""
        with open(self.profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return CandidateProfile.model_validate(data)



