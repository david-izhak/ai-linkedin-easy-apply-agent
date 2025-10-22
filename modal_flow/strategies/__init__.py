"""
Concrete strategy implementations for rule execution.
"""

from .base import IStrategy, BaseStrategy
from .literal import LiteralStrategy
from .numeric import NumericFromProfileStrategy
from .one_of_options import OneOfOptionsStrategy, OneOfOptionsFromProfileStrategy
from .profile_key import ProfileKeyStrategy
from .salary_by_currency import SalaryByCurrencyStrategy


STRATEGY_MAPPING = {
    "literal": LiteralStrategy,
    "profile_key": ProfileKeyStrategy,
    "numeric_from_profile": NumericFromProfileStrategy,
    "one_of_options": OneOfOptionsStrategy,
    "one_of_options_from_profile": OneOfOptionsFromProfileStrategy,
    "salary_by_currency": SalaryByCurrencyStrategy,
}


def create_strategy(strategy_kind: str, params: dict, **kwargs) -> BaseStrategy:
    strategy_class = STRATEGY_MAPPING.get(strategy_kind)
    if not strategy_class:
        raise ValueError(f"Unknown strategy kind: {strategy_kind}")
    return strategy_class(params=params, **kwargs)


__all__ = [
    "LiteralStrategy",
    "ProfileKeyStrategy",
    "NumericFromProfileStrategy",
    "OneOfOptionsStrategy",
]

