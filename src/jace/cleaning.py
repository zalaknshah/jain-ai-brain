"""Explicit, typed cleaning preferences and authored plans; no inference or action."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass

from .model_output import strict_json
from .models import Memory

PROFILE_SOURCE = 'cleaning_profile_v1'
SURFACES = {'wooden_furniture': 'wooden furniture', 'hard_floor': 'a hard floor', 'general': 'the selected surface'}
WATER_POLICIES = {'avoid', 'follow_surface_guidance'}
SUPPLIES_POLICIES = {'existing_only', 'review_missing'}


@dataclass(frozen=True)
class CleaningProfile:
    surface: str
    water_policy: str
    time_budget_minutes: int
    supplies_policy: str

    def to_dict(self) -> dict:
        return asdict(self)


def validate_profile(value: dict) -> CleaningProfile:
    if not isinstance(value, dict) or set(value) != {'surface', 'water_policy', 'time_budget_minutes', 'supplies_policy'}:
        raise ValueError('cleaning profile requires exactly surface, water_policy, time_budget_minutes and supplies_policy')
    for key, choices in (('surface', SURFACES), ('water_policy', WATER_POLICIES), ('supplies_policy', SUPPLIES_POLICIES)):
        if not isinstance(value[key], str) or value[key] not in choices:
            raise ValueError(f'invalid cleaning profile {key}')
    minutes = value['time_budget_minutes']
    if type(minutes) is not int or not 1 <= minutes <= 120:
        raise ValueError('time_budget_minutes must be an integer from 1 through 120')
    return CleaningProfile(**value)


def encode_profile(profile: CleaningProfile) -> str:
    return json.dumps({'version': 1, 'profile': profile.to_dict()}, sort_keys=True, separators=(',', ':'))


def decode_profile(memory: Memory) -> CleaningProfile:
    if memory.source != PROFILE_SOURCE or not isinstance(memory.content, str) or len(memory.content) > 2048:
        raise ValueError('memory is not a supported typed cleaning profile')
    value = strict_json(memory.content)
    if not isinstance(value, dict) or set(value) != {'version', 'profile'} or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('stored cleaning profile is malformed; review and explicitly replace it')
    return validate_profile(value['profile'])


def build_plan(profile: CleaningProfile) -> dict:
    # Revalidate typed values so direct Python callers cannot bypass admission
    # by constructing a dataclass with incorrect runtime types.
    profile = validate_profile(profile.to_dict())
    surface = SURFACES[profile.surface]
    steps = [
        {'id': 'inspect', 'instruction': f'Inspect a small area of {surface} before contact. If living beings are present, pause and leave a clear route. Do not assume that none are present because you cannot see them.'},
        {'id': 'check_guidance', 'instruction': 'Check the surface and product instructions first. If the material/finish is unknown, or there is mold, bodily fluid, another contamination concern or a need for disinfection, pause this routine-cleaning plan and seek the appropriate qualified guidance. Do not mix cleaning products.'},
    ]
    if profile.water_policy == 'avoid':
        steps.append({'id': 'water_constraint', 'instruction': 'Keep water and liquid cleaning products out of this plan. Check whether the surface instructions permit an appropriate dry method; do not assume brushing or rubbing is safe. If the no-water constraint prevents necessary hygiene, pause rather than silently relaxing the constraint or skipping hygiene.'})
    else:
        steps.append({'id': 'water_constraint', 'instruction': 'Choose only a method permitted by the surface and product instructions. This profile does not establish that water or any cleaning agent is safe for the surface. Do not add water by default or improvise a mixture.'})
    if profile.supplies_policy == 'existing_only':
        steps.append({'id': 'supplies_constraint', 'instruction': 'Use only already-owned supplies that the instructions identify as suitable. If suitable supplies are unavailable, pause; do not substitute an unsuitable item or buy something as part of this plan.'})
    else:
        steps.append({'id': 'supplies_constraint', 'instruction': 'Check suitable supplies already owned. If an essential item is missing, make a short list for your review before any purchase or use. This plan neither orders nor authorizes a purchase.'})
    steps.extend([
        {'id': 'time_constraint', 'instruction': f'Set aside at most {profile.time_budget_minutes} minute(s) for this session, including inspection and checking instructions. Select only a small section that can be paused safely; this is a time preference, not a claim that the task can be completed within it.'},
        {'id': 'review', 'instruction': 'Only proceed if the required checks support the method. Check the result before repeating or expanding work. Stop when the time budget is reached or new uncertainty appears, and reassess rather than rushing.'},
    ])
    return {'task': 'routine_cleaning', 'profile_applied': profile.to_dict(), 'steps': steps,
            'actions_executed': False, 'action': None,
            'limits': ['Authored conditional checklist, not a learned or optimized cleaning plan.',
                       'Profile choices are user declarations, not verified surface, product or environmental observations.',
                       'No surface assessment, hygiene qualification, zero-harm guarantee, provider call, purchase or robot command.']}
