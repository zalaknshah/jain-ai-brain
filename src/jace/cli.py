from __future__ import annotations

import argparse
import json
import sys

from .api import serve
from .engine import CognitiveEngine


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="jace", description="Jain AI Cognitive Engine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health")
    ask = sub.add_parser("ask")
    ask.add_argument("input")
    ask.add_argument("--user", default="local-user")
    ask.add_argument("--learn", action="store_true", help="persist only an explicit preference/fact in this turn")
    remember = sub.add_parser("remember")
    remember.add_argument("user_id")
    remember.add_argument("content")
    sub.add_parser("serve")
    args = parser.parse_args()

    if args.command == "serve":
        serve()
        return
    engine = CognitiveEngine()
    try:
        if args.command == "health":
            print(json.dumps({"status": "ok", "canonical_entries": len(engine.canonical.all()), "reasoner": type(engine.reasoner).__name__, "graph": engine.graph.stats()}, indent=2))
        elif args.command == "ask":
            result = engine.think(args.user, args.input)
            payload = result.to_dict()
            if args.learn:
                memory, notes = engine.learn_from_conversation(args.user, args.input)
                payload["learned_memory"] = memory.to_dict() if memory else None
                payload["learning_notes"] = notes
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        elif args.command == "remember":
            memory, notes = engine.remember(args.user_id, args.content)
            print(json.dumps({"accepted": memory is not None, "memory": memory.to_dict() if memory else None, "notes": notes}, indent=2))
    finally:
        engine.close()


if __name__ == "__main__":
    main()
