from __future__ import annotations

import argparse
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.serve import (
    DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
    DEFAULT_EQUITY_CATCHUP_INTERVAL_MINUTES,
    DEFAULT_EQUITY_INTERVAL_MINUTES,
)


DEFAULT_LABEL = "com.changming.treasury-factor-desk"
DEFAULT_PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_LOG_DIR = Path.home() / "Library" / "Logs" / "treasury-factor-desk"


def build_launch_agent_plist(
    *,
    label: str,
    python_path: Path,
    daily_at: str,
    port: int,
    log_dir: Path,
    equity_interval_minutes: float = DEFAULT_EQUITY_INTERVAL_MINUTES,
    equity_catchup_interval_minutes: float = DEFAULT_EQUITY_CATCHUP_INTERVAL_MINUTES,
    equity_after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
) -> bytes:
    output_path = PROJECT_ROOT / "data" / "dashboard.json"
    server_command = [
        str(python_path),
        str(PROJECT_ROOT / "scripts" / "serve.py"),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--daily-at",
        daily_at,
        "--equity-interval-minutes",
        f"{equity_interval_minutes:g}",
        "--equity-catchup-interval-minutes",
        f"{equity_catchup_interval_minutes:g}",
        "--equity-after-close-lag-minutes",
        str(equity_after_close_lag_minutes),
        "--output",
        str(output_path),
    ]
    command = "exec " + " ".join(shlex.quote(part) for part in server_command)
    program_arguments = ["/bin/zsh", "-lc", command]
    payload = {
        "Label": label,
        "ProgramArguments": program_arguments,
        # launchd is strict about directly spawned programs; using the system
        # shell keeps the agent bootstrap stable while preserving the final
        # server process through exec.
        # Keep launchd out of Desktop/Documents as its cwd; the server uses
        # absolute paths and serves PROJECT_ROOT explicitly.
        "WorkingDirectory": str(Path.home()),
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(log_dir / "launchd.out.log"),
        "StandardErrorPath": str(log_dir / "launchd.err.log"),
    }
    return plistlib.dumps(payload, sort_keys=False)


def install_launch_agent(
    *,
    label: str = DEFAULT_LABEL,
    daily_at: str = "16:30",
    port: int = 8451,
    equity_interval_minutes: float = DEFAULT_EQUITY_INTERVAL_MINUTES,
    equity_catchup_interval_minutes: float = DEFAULT_EQUITY_CATCHUP_INTERVAL_MINUTES,
    equity_after_close_lag_minutes: int = DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES,
    plist_dir: Path = DEFAULT_PLIST_DIR,
    load: bool = False,
) -> Path:
    plist_dir.mkdir(parents=True, exist_ok=True)
    log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{label}.plist"
    plist_path.write_bytes(
        build_launch_agent_plist(
            label=label,
            python_path=Path(sys.executable).resolve(),
            daily_at=daily_at,
            port=port,
            log_dir=log_dir,
            equity_interval_minutes=equity_interval_minutes,
            equity_catchup_interval_minutes=equity_catchup_interval_minutes,
            equity_after_close_lag_minutes=equity_after_close_lag_minutes,
        )
    )
    if load:
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return plist_path


def uninstall_launch_agent(label: str = DEFAULT_LABEL, plist_dir: Path = DEFAULT_PLIST_DIR) -> Path:
    plist_path = plist_dir / f"{label}.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
        plist_path.unlink()
    return plist_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the Treasury dashboard macOS background updater")
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--daily-at", default="16:30")
    parser.add_argument("--port", type=int, default=8451)
    parser.add_argument("--equity-interval-minutes", type=float, default=DEFAULT_EQUITY_INTERVAL_MINUTES)
    parser.add_argument("--equity-catchup-interval-minutes", type=float, default=DEFAULT_EQUITY_CATCHUP_INTERVAL_MINUTES)
    parser.add_argument("--equity-after-close-lag-minutes", type=int, default=DEFAULT_EQUITY_AFTER_CLOSE_LAG_MINUTES)
    parser.add_argument("--load", action="store_true", help="Load the LaunchAgent immediately after writing it")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    if args.uninstall:
        plist_path = uninstall_launch_agent(label=args.label)
        print(f"Removed {plist_path}")
        return 0

    plist_path = install_launch_agent(
        label=args.label,
        daily_at=args.daily_at,
        port=args.port,
        equity_interval_minutes=args.equity_interval_minutes,
        equity_catchup_interval_minutes=args.equity_catchup_interval_minutes,
        equity_after_close_lag_minutes=args.equity_after_close_lag_minutes,
        load=args.load,
    )
    print(f"Wrote {plist_path}")
    if args.load:
        print(f"Loaded {args.label}; dashboard will serve at http://127.0.0.1:{args.port}/")
    else:
        print(f"Load with: launchctl load {plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
