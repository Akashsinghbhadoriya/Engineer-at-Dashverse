import asyncio
import time
from orchestrator import Orchestrator
from workflow import build_travel_graph


def print_trace(trace):
    print("\n  Execution Trace:")
    for entry in trace:
        print(f"    [{entry['state']:10}] {entry['node']}  @ t+{entry['timestamp']:.3f}s")


async def run_scenario(name, user_input, scenario="happy_path"):
    print(f"\n{'=' * 55}")
    print(f"SCENARIO : {name}  (mock: '{scenario}')")
    print(f"Input    : {user_input}")

    graph = build_travel_graph(scenario=scenario)
    start = time.time()
    result = await Orchestrator().run(graph, user_input)
    elapsed = (time.time() - start) * 1000

    print_trace(result["trace"])
    print(f"\n  Response : {result['response']}")
    print(f"  Duration : {elapsed:.0f}ms")


async def main():
    # 1. All providers succeed — pick cheapest
    await run_scenario(
        "Happy Path",
        "Book me a flight from New York to Paris today for vacation",
        scenario="happy_path",
    )

    # 2. United fails permanently — best of AirFrance + Delta returned
    await run_scenario(
        "Partial Failure (United down)",
        "Book me a flight from New York to Paris today for vacation",
        scenario="partial_failure",
    )

    # 3. All providers fail → aggregator skips → formatter produces apology
    await run_scenario(
        "All Providers Fail",
        "Book me a flight from New York to Paris today for vacation",
        scenario="all_fail",
    )

    # 4. Delta fails twice, succeeds on 3rd attempt (retry_policy.max_attempts=3)
    await run_scenario(
        "Retry Then Succeed (Delta transient)",
        "Book me a flight from New York to Paris today for vacation",
        scenario="retry_then_succeed",
    )

    # 5. Vague query — parser extracts nothing, validator flags missing fields
    await run_scenario(
        "Missing Info",
        "I want to travel somewhere",
        scenario="happy_path",
    )


if __name__ == "__main__":
    asyncio.run(main())
