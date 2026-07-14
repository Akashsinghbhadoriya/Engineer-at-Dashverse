import asyncio
import time
from orchestrator import Orchestrator
from workflow import build_travel_graph

LINE  = "─" * 72
DLINE = "═" * 72


def print_trace_table(trace, wall_ms, total_providers):
    responded = sum(
        1 for t in trace
        if t["node"].startswith("provider_") and t["state"] == "COMPLETED"
    )
    col = "{:<26} {:<12} {:<14} {:<14} {:<10}"
    print(f"\n{LINE * 1}")
    print("  EXECUTION TRACE")
    print(LINE)
    print("  " + col.format("Node", "Status", "Duration", "Attempts", "Parallel"))
    print(LINE)
    for t in trace:
        status  = "✓  OK"    if t["state"] == "COMPLETED" else \
                  "✗  FAIL"  if t["state"] == "FAILED"    else \
                  "—  SKIP"
        dur     = f"{t['duration_ms']:.1f}ms" if t["state"] != "SKIPPED" else "—"
        attempts = f"{t['attempts']}/{t['max_attempts']}"
        parallel = "Yes" if t["parallel"] else "No"
        print("  " + col.format(t["label"], status, dur, attempts, parallel))
    print(LINE)
    print(f"  Total wall time: {wall_ms:.1f}ms  |  {responded}/{total_providers} providers responded")
    print(LINE)


async def run_scenario(title, user_input, scenario="happy_path", total_providers=3):
    print(f"\n{DLINE}")
    print(f"  TEST: {title}")
    print(f"  Input: \"{user_input}\"")
    print(LINE)
    print("  Live execution:\n")

    graph = build_travel_graph(scenario=scenario)
    start = time.time()
    result = await Orchestrator().run(graph, user_input)
    wall_ms = (time.time() - start) * 1000

    print(f"\n{LINE}")
    print("  RESULT:")
    response = result["response"] or "No response generated."
    for line in response.splitlines():
        print(f"    {line}")

    print_trace_table(result["trace"], wall_ms, total_providers)


async def main():
    await run_scenario(
        "Happy Path — All 3 Providers Succeed",
        "Book a flight from new york to paris today for vacation",
        scenario="happy_path",
    )

    await run_scenario(
        "Partial Failure — United fails permanently",
        "Book a flight from new york to paris today for vacation",
        scenario="partial_failure",
    )

    await run_scenario(
        "All Providers Fail",
        "Book a flight from new york to paris today for vacation",
        scenario="all_fail",
    )

    await run_scenario(
        "Retry Then Succeed — Delta transient failure",
        "Book a flight from new york to paris today for vacation",
        scenario="retry_then_succeed",
    )

    await run_scenario(
        "Validation Failure — Missing fields",
        "I want to travel somewhere",
        scenario="happy_path",
    )


if __name__ == "__main__":
    asyncio.run(main())
