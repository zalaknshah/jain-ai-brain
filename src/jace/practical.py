"""Small, authored scenario plans, not a model or a religious knowledge base."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .text import lexical_terms
from .language_support import PLANS, native_plan_key, response_language, script_cues


@dataclass(frozen=True)
class PracticalPlan:
    name: str
    retrieval_terms: str
    steps: tuple[str, ...]
    tradeoff: str
    question: str
    language: str = 'en'


_CLEANING = PracticalPlan(
    "Household cleaning",
    "ahimsa aparigraha living beings resources gentle reversible",
    (
        "Inspect a small area first. If insects are present, pause and leave them a clear route before cleaning.",
        "Reuse a suitable soft brush or cloth when appropriate for the surface. Follow the product and surface instructions; do not mix cleaners.",
        "Clean only the area that needs attention, using the amount of water and product required for the task rather than extra by default.",
        "Check the result before repeating or expanding the work. Keep the plan reversible where possible.",
    ),
    "Reducing materials must not compromise necessary hygiene or surface safety. I cannot assess contamination or living organisms remotely, and cannot promise zero harm.",
    "Which surfaces are involved, and is this routine cleaning or a contamination concern?",
)
_WARDROBE = PracticalPlan(
    "Wardrobe organization",
    "aparigraha restraint accumulation resources reversible",
    (
        "Inventory what you already wear and what your work, climate, health and beliefs require before deciding what is excess.",
        "Repair, re-wear and recombine suitable clothes. Try the storage you already own before buying organizers.",
        "Set uncertain items aside for a review period instead of immediately discarding them. Check ownership before changing anyone else's belongings.",
        "With the owner's agreement, offer usable surplus to a willing recipient or donation service that accepts it. Buy only after identifying a specific unmet need.",
    ),
    "Fewer possessions are not automatically better if necessary clothing is lost or replacements create more consumption. A suitable minimum depends on your circumstances.",
    "What do you regularly wear, and which practical needs or sentimental items should the plan preserve?",
)
_DISPUTE = PracticalPlan(
    "Business-partner disagreement",
    "anekantavada perspective uncertainty evidence ahimsa speech de-escalation",
    (
        "Separate agreed facts from interpretations. Write down the specific decision in dispute without assuming the other person's motives.",
        "Ask your partner to explain their concerns, then summarize their view and invite correction before presenting yours.",
        "Identify shared interests and each person's constraints. Compare at least two workable options rather than treating the disagreement as a contest.",
        "Propose a small, reversible trial with a review date only if both parties agree. Keep any new commitments explicit.",
    ),
    "Considering another viewpoint does not establish disputed facts or require accepting coercion. Legal rights, formal deadlines and binding commitments need qualified advice, not this prototype.",
    "What decision is disputed, what outcome does each person want, and are there urgent constraints?",
)


def _english_plan_keys(words: set[str]) -> set[str]:
    matches = set()
    if words & {"clean", "cleaning", "sweep", "sweeping"} and words & {"house", "home", "room", "rooms", "floor", "floors"}:
        matches.add('cleaning')
    if words & {"wardrobe", "closet"} and words & {"organize", "organise", "organizing", "organising", "declutter", "decluttering", "tidy"}:
        matches.add('wardrobe')
    if words & {"dispute", "disagreement", "conflict", "argue", "argument"} and {"business", "partner"} <= words:
        matches.add('dispute')
    return matches


def plan_for(request: str) -> PracticalPlan | None:
    """Recognize only the three bounded household/work examples in the brief."""
    words = lexical_terms(request)
    # Conservative exclusions for known non-household and negated examples.
    # These are lexical guards, not general intent or negation understanding.
    if words & {"code", "software", "database", "repository", "dataset", "programming"}:
        return None
    if re.search(r"\b(?:do not|don't|don’t|never)\s+(?:clean|sweep|organize|organise|declutter|tidy)\b", request, re.I):
        return None
    plans = {'cleaning': _CLEANING, 'wardrobe': _WARDROBE, 'dispute': _DISPUTE}
    english_keys = _english_plan_keys(words)
    language = response_language(request)
    if language in PLANS:
        key = native_plan_key(request)
        # Do not discard a second supported task simply because it was written
        # in English. Repetition of the same scenario is not a second task.
        if key is None or len(english_keys | {key}) != 1:
            return None
        original = plans[key]
        name, steps, tradeoff, question = PLANS[language][key]
        return PracticalPlan(name, original.retrieval_terms, steps, tradeoff, question, language)
    # Mixed Gujarati/Devanagari is not silently assigned a language or plan.
    if all(script_cues(request)):
        return None
    # Avoid pretending a single plan handles a compound or ambiguous request.
    return plans[next(iter(english_keys))] if len(english_keys) == 1 else None
