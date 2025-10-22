import asyncio
import logging
import os
import sys

# Ensure project root is in sys.path so 'modal_flow' package can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modal_flow.rules_store import RuleStore
from modal_flow.profile_store import ProfileStore
from modal_flow.normalizer import QuestionNormalizer
from modal_flow.rules_engine import RulesEngine


async def main():
    logging.basicConfig(level=logging.DEBUG)

    profile_store = ProfileStore("config/profile_example.json")
    profile = profile_store.load()

    rule_store = RuleStore("config/rules.yaml")
    normalizer = QuestionNormalizer("config/normalizer_rules.yaml")

    engine = RulesEngine(profile=profile, rule_store=rule_store, normalizer=normalizer)

    question = "How many years of Python experience do you have?"
    decision = await engine.decide(question=question, field_type="number", options=None)
    print("Decision:", decision)


if __name__ == '__main__':
    asyncio.run(main())
