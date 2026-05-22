from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sandbox.sportradar_stats.capture_everything import capture_everything
from sandbox.sportradar_stats.capture_runtime import resolve_capture_user_data_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the working Playwright capture in headless mode, optionally reusing a real browser profile.",
    )
    parser.add_argument("stats_url")
    parser.add_argument(
        "--bootstrap-url",
        default=None,
    )
    parser.add_argument(
        "--seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("sandbox/sportradar_stats/captures/headless_capture"),
    )
    parser.add_argument(
        "--user-data-dir",
        default=None,
        help="Optional persistent Chrome/Chromium profile. If omitted, the script auto-detects known local profiles.",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    user_data_dir = resolve_capture_user_data_dir(args.user_data_dir)
    print(f"Headless capture profile: {user_data_dir or 'none'}")

    await capture_everything(
        args.stats_url,
        out_dir=args.out_dir,
        seconds=args.seconds,
        headless=True,
        user_data_dir=user_data_dir,
        bootstrap_url=args.bootstrap_url,
    )


if __name__ == "__main__":
    asyncio.run(main())
