"""CI diagnostic: print agent_framework import details and any silent failures."""

import sys
import traceback


def main() -> None:
    try:
        import agent_framework as af
    except Exception:
        print("IMPORT_FAILED:")
        traceback.print_exc()
        sys.exit(0)

    print("IMPORT_OK:", af.__file__)
    print("INIT_SIZE:", __import__("os").path.getsize(af.__file__))

    attrs = [x for x in dir(af) if not x.startswith("_")]
    print("DIR_COUNT:", len(attrs))
    print("FIRST_20_ATTRS:", attrs[:20])

    for sym in (
        "AgentResponse",
        "FunctionTool",
        "tool",
        "Executor",
        "Workflow",
        "WorkflowBuilder",
        "WorkflowContext",
        "handler",
    ):
        present = sym in attrs
        print(f"  {sym}: {present}")
        if not present:
            try:
                exec(f"from agent_framework import {sym}", {})
                print(f"    (from-import works for {sym})")
            except Exception:
                print(f"    (from-import FAILED for {sym}):")
                traceback.print_exc()


if __name__ == "__main__":
    main()
