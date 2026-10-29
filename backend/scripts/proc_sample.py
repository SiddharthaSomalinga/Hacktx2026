"""Samples CPU and memory of matching processes once a second, then prints a summary (D61).

    uv run python -m scripts.proc_sample --pid <uvicorn's pid> --seconds 70
    uv run python -m scripts.proc_sample --match "uvicorn app.main:build" --seconds 70

Run beside `load_check`, so a run's numbers come with what the server spent. `--pid` follows a
process and its children: uvicorn's workers are spawned by multiprocessing, so their command
lines don't name the app. CPU is `ps`'s %CPU (100 = one core); on the deploy, run it inside
the container with `docker exec`.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from collections import defaultdict


def sample(match: str | None, root: int | None) -> dict[int, tuple[float, int]]:
    """{pid: (%cpu, rss KiB)} for `root` and its descendants, or for every process whose
    command line contains `match`."""
    out = subprocess.run(
        ["ps", "-A", "-o", "pid=,ppid=,pcpu=,rss=,command="],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    rows = [line.split(None, 4) for line in out.splitlines()]
    tree = {root} if root is not None else set()
    grew = True
    while grew:  # parents can be listed after their children
        grew = False
        for pid, ppid, *_ in rows:
            if int(ppid) in tree and int(pid) not in tree:
                tree.add(int(pid))
                grew = True
    found: dict[int, tuple[float, int]] = {}
    for pid, _, cpu, rss, command in rows:
        chosen = int(pid) in tree if root is not None else match is not None and match in command
        if chosen and "proc_sample" not in command:
            found[int(pid)] = (float(cpu), int(rss))
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--match", help="a substring of the command line")
    which.add_argument("--pid", type=int, help="a process; its children are included")
    parser.add_argument("--seconds", type=float, default=60)
    args = parser.parse_args(argv)
    cpu: dict[int, list[float]] = defaultdict(list)
    rss: dict[int, int] = defaultdict(int)
    stop = time.monotonic() + args.seconds
    while time.monotonic() < stop:
        for pid, (c, r) in sample(args.match, args.pid).items():
            cpu[pid].append(c)
            rss[pid] = max(rss[pid], r)
        time.sleep(1)
    total = [sum(xs) for xs in zip(*cpu.values(), strict=False)] if cpu else []
    for pid in sorted(cpu):
        xs = cpu[pid]
        print(
            f"pid {pid}: CPU mean {statistics.mean(xs):.0f}% max {max(xs):.0f}%,"
            f" RSS max {rss[pid] / 1024:.0f} MiB"
        )
    if total:
        print(f"all: CPU mean {statistics.mean(total):.0f}% max {max(total):.0f}% of one core")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
