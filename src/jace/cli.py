from __future__ import annotations

import argparse
import json
import sys

from .api import serve
from .engine import CognitiveEngine
from .cleaning import SURFACES, WATER_POLICIES, SUPPLIES_POLICIES, validate_profile
from .temporal import normalize_expiration
from .memory_scope import validate_memory_scope
from .simulator import run_scenarios
from .physics import SCENARIOS, run_physics_scenario
from .articulated import ARTICULATION_SCENARIOS, run_articulation_scenario
from .reaching import plan_hand_target, run_hand_target
from .freebase import SCENARIOS as FREEBASE_SCENARIOS, run_freebase_diagnostic


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="jace", description="Jain AI Cognitive Engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    ask = sub.add_parser("ask")
    ask.add_argument("input")
    ask.add_argument("--user", default="local-user")
    ask.add_argument("--memory-scope", type=validate_memory_scope, default="default")
    ask.add_argument("--learn", action="store_true", help="persist only an explicit preference/fact in this turn")
    remember = sub.add_parser("remember")
    remember.add_argument("user_id")
    remember.add_argument("content")
    remember.add_argument("--memory-scope", type=validate_memory_scope, default="default")
    remember.add_argument('--expires-at', help='stop future recall at this explicit timezone timestamp; does not delete the record')
    expiry = sub.add_parser('set-memory-expiration', help='explicitly change recall expiry for one owned memory; does not delete it')
    expiry.add_argument('user_id')
    expiry.add_argument('memory_id', type=int)
    expiry_choice = expiry.add_mutually_exclusive_group(required=True)
    expiry_choice.add_argument('--at', help='ISO timestamp with an explicit timezone')
    expiry_choice.add_argument('--never', action='store_true', help='remove expiration, allowing this memory to be recalled again')
    correct = sub.add_parser("correct-memory")
    correct.add_argument("user_id")
    correct.add_argument("memory_id", type=int)
    correct.add_argument("content")
    memories = sub.add_parser("memories", help="review the owner's recent memory IDs and contents")
    memories.add_argument("user_id")
    memories.add_argument("--memory-scope", type=validate_memory_scope, default="default")
    scopes = sub.add_parser("memory-scopes", help="list this owner's named memory scopes")
    scopes.add_argument("user_id")
    forget = sub.add_parser("forget-memory", help="preview deletion of one owned memory; confirmation is required")
    forget.add_argument("user_id")
    forget.add_argument("memory_id", type=int)
    forget.add_argument("--confirm-delete", action="store_true", help="delete this exact owned memory after reviewing its preview")
    forget.add_argument("--confirm-all-unattributed-audit-cleanup", action="store_true",
                        help="also delete ALL of this owner's unattributed audit entries, including legacy entries; preserves other active memories and attributable audits")
    for command in ('save-cleaning-profile', 'update-cleaning-profile'):
        profile = sub.add_parser(command, help='preview or explicitly save a typed routine-cleaning preference profile')
        profile.add_argument('user_id')
        if command == 'update-cleaning-profile':
            profile.add_argument('memory_id', type=int)
            profile.add_argument('--expected-revision', required=True)
        else:
            profile.add_argument('--memory-scope', type=validate_memory_scope, default='default')
            profile.add_argument('--expires-at')
        profile.add_argument('--surface', choices=sorted(SURFACES), required=True)
        profile.add_argument('--water-policy', choices=sorted(WATER_POLICIES), required=True)
        profile.add_argument('--time-budget-minutes', type=int, required=True)
        profile.add_argument('--supplies-policy', choices=sorted(SUPPLIES_POLICIES), required=True)
        profile.add_argument('--confirm-save', action='store_true', help='explicitly persist these choices for future local cleaning plans')
    cleaning = sub.add_parser('plan-cleaning', help='build a local conditional checklist from an explicitly saved profile; no actions')
    cleaning.add_argument('user_id')
    cleaning.add_argument('--memory-scope', type=validate_memory_scope, default='default')
    cleaning.add_argument('--profile-memory-id', type=int)
    sub.add_parser("serve")
    sub.add_parser("simulate")
    physics = sub.add_parser("simulate-physics", help="run the optional bounded MuJoCo slider fixture; no hardware")
    physics.add_argument("--scenario", choices=SCENARIOS, default="clear_path")
    physics.add_argument("--steps", type=int, default=500)
    physics.add_argument("--confirm-simulation", action="store_true", help="allow bounded actuation in this simulation only")
    physics.add_argument("--trace", action="store_true", help="include per-step observations and decisions")
    articulation = sub.add_parser("simulate-articulation", help="run the original fixed-base nine-joint fixture; no gait or hardware")
    articulation.add_argument("--scenario", choices=ARTICULATION_SCENARIOS, default="clear_path")
    articulation.add_argument("--steps", type=int, default=1000)
    articulation.add_argument("--confirm-simulation", action="store_true")
    articulation.add_argument("--trace", action="store_true")
    reach = sub.add_parser("simulate-reach", help="plan a world-coordinate left-hand target for the fixed-base fixture")
    reach.add_argument("--target", nargs=3, type=float, required=True, metavar=("X", "Y", "Z"))
    reach.add_argument("--scenario", choices=ARTICULATION_SCENARIOS, default="clear_path")
    reach.add_argument("--steps", type=int, default=1000)
    reach.add_argument("--confirm-simulation", action="store_true")
    reach.add_argument("--plan-only", action="store_true", help="verify endpoint kinematics without any dynamics steps")
    reach.add_argument("--trace", action="store_true")
    freebase = sub.add_parser("diagnose-freebase", help="resource-capped modified G1 posture/fall diagnostic, not gait")
    freebase.add_argument("--scenario", choices=FREEBASE_SCENARIOS, default="neutral_posture")
    freebase.add_argument("--steps", type=int, default=1250)
    freebase.add_argument("--confirm-simulation", action="store_true")
    freebase.add_argument("--trace", action="store_true")
    args = parser.parse_args()

    if args.command == "serve":
        serve()
        return
    if args.command == "diagnose-freebase":
        try:
            result = run_freebase_diagnostic(args.scenario, steps=args.steps,
                                            confirm_simulation=args.confirm_simulation, include_trace=args.trace)
        except (ValueError, RuntimeError) as error:
            parser.exit(2, str(error) + "\n")
        print(json.dumps(result, indent=2))
        return
    if args.command == "simulate-reach":
        try:
            if args.plan_only:
                result = {"plan": plan_hand_target(args.target).to_dict(), "dynamics_executed": False}
            else:
                result = run_hand_target(args.target, scenario=args.scenario, steps=args.steps,
                                         confirm_simulation=args.confirm_simulation).to_dict(include_trace=args.trace)
        except (ValueError, RuntimeError) as error:
            parser.exit(2, str(error) + "\n")
        print(json.dumps(result, indent=2))
        return
    if args.command == "simulate-articulation":
        try:
            report = run_articulation_scenario(args.scenario, steps=args.steps, confirm_simulation=args.confirm_simulation)
        except (ValueError, RuntimeError) as error:
            parser.exit(2, str(error) + "\n")
        print(json.dumps(report.to_dict(include_trace=args.trace), indent=2))
        return
    if args.command == "simulate-physics":
        try:
            report = run_physics_scenario(args.scenario, steps=args.steps, confirm_simulation=args.confirm_simulation)
        except (ValueError, RuntimeError) as error:
            parser.exit(2, str(error) + "\n")
        print(json.dumps(report.to_dict(include_trace=args.trace), indent=2))
        return
    if args.command == "simulate":
        print(json.dumps(run_scenarios(), indent=2))
        return
    engine = CognitiveEngine()
    try:
        if args.command == "health":
            print(json.dumps({"status": "ok", "canonical_entries": len(engine.canonical.all()), "reasoner": type(engine.reasoner).__name__, "graph": engine.graph.stats()}, indent=2))
        elif args.command == "ask":
            result = engine.think(args.user, args.input, memory_scope=args.memory_scope)
            payload = result.to_dict()
            if args.learn:
                memory, notes = engine.learn_from_conversation(args.user, args.input, memory_scope=args.memory_scope)
                payload["learned_memory"] = memory.to_dict() if memory else None
                payload["learning_notes"] = notes
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.command in ('save-cleaning-profile', 'update-cleaning-profile'):
            try:
                profile = validate_profile(dict(surface=args.surface, water_policy=args.water_policy,
                    time_budget_minutes=args.time_budget_minutes, supplies_policy=args.supplies_policy)).to_dict()
                if not args.user_id.strip():
                    raise ValueError('user_id is required')
                if not args.confirm_save:
                    result = {'saved': False, 'profile': profile, 'requires_confirm_save': True,
                        'note': 'Review these explicit choices, then add --confirm-save. No profile has been persisted.'}
                    if args.command == 'save-cleaning-profile':
                        result.update(memory_scope=args.memory_scope, expires_at=normalize_expiration(args.expires_at))
                elif args.command == 'save-cleaning-profile':
                    memory, notes = engine.save_cleaning_profile(args.user_id, profile, confirm_save=True,
                        memory_scope=args.memory_scope, expires_at=args.expires_at)
                    result = {'saved': memory is not None, 'memory': memory.to_dict() if memory else None, 'notes': notes}
                else:
                    memory, notes = engine.update_cleaning_profile(args.user_id, args.memory_id, profile,
                        expected_revision=args.expected_revision, confirm_save=True)
                    result = {'saved': memory is not None, 'memory': memory.to_dict() if memory else None, 'notes': notes}
                print(json.dumps(result, indent=2))
            except (LookupError, ValueError) as error:
                parser.exit(2, str(error) + '\n')
        elif args.command == 'plan-cleaning':
            try:
                print(json.dumps(engine.plan_cleaning(args.user_id, memory_scope=args.memory_scope,
                    profile_memory_id=args.profile_memory_id), indent=2, ensure_ascii=False))
            except (LookupError, ValueError) as error:
                parser.exit(2, str(error) + '\n')
        elif args.command == "correct-memory":
            memory, notes = engine.correct_memory(args.user_id, args.memory_id, args.content)
            print(json.dumps({"accepted": memory is not None, "memory": memory.to_dict() if memory else None, "notes": notes}, indent=2))
        elif args.command == 'set-memory-expiration':
            try:
                memory = engine.set_memory_expiration(args.user_id, args.memory_id, args.at)
                print(json.dumps({'memory': memory.to_dict(), 'note': 'Expiration controls future recall, not storage or deletion.'}, indent=2))
            except (LookupError, ValueError) as error:
                parser.exit(2, str(error) + '\n')
        elif args.command == "remember":
            memory, notes = engine.remember(args.user_id, args.content, expires_at=args.expires_at, memory_scope=args.memory_scope)
            print(json.dumps({"accepted": memory is not None, "memory": memory.to_dict() if memory else None, "notes": notes}, indent=2))
        elif args.command == "memories":
            print(json.dumps({'memories': [memory.to_dict() for memory in engine.list_memories(args.user_id, memory_scope=args.memory_scope)]}, indent=2))
        elif args.command == "memory-scopes":
            print(json.dumps({"memory_scopes": engine.list_memory_scopes(args.user_id)}, indent=2))
        elif args.command == "forget-memory":
            try:
                if not args.confirm_delete:
                    result = engine.preview_memory_deletion(args.user_id, args.memory_id)
                    result['deleted'] = 0
                    result['next_step'] = 'Review the warning, then repeat with --confirm-delete. If required, explicitly add --confirm-all-unattributed-audit-cleanup to accept loss of ALL unattributed audit entries for this owner.'
                else:
                    deleted = engine.forget_memory(args.user_id, args.memory_id, confirm_delete=True,
                        confirm_unattributed_audit_cleanup=args.confirm_all_unattributed_audit_cleanup)
                    result = {'deleted': deleted, 'memory_id': args.memory_id, 'user_id': args.user_id}
                print(json.dumps(result, indent=2))
            except (LookupError, ValueError) as error:
                parser.exit(2, str(error) + '\n')
    finally:
        engine.close()


if __name__ == "__main__":
    main()
