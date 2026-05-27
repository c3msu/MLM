from __future__ import annotations

import argparse
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABEL = "com.changming.treasury-factor-desk-health"
DEFAULT_PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
DEFAULT_LOG_DIR = Path.home() / "Library" / "Logs" / "treasury-factor-desk"


def parse_daily_at(daily_at: str) -> tuple[int, int]:
    hour_text, minute_text = daily_at.split(":", 1)
    return int(hour_text), int(minute_text)


def build_health_agent_plist(
    *,
    label: str,
    python_path: Path,
    daily_at: str,
    port: int,
    log_dir: Path,
    notify: bool,
) -> bytes:
    hour, minute = parse_daily_at(daily_at)
    url = f"http://127.0.0.1:{port}/api/health"
    health_command = [
        str(python_path),
        str(PROJECT_ROOT / "scripts" / "check_health.py"),
        "--url",
        url,
    ]
    if notify:
        health_command.append("--notify")
    command = "exec " + " ".join(shlex.quote(part) for part in health_command)
    program_arguments = ["/bin/zsh", "-lc", command]
    payload = {
        "Label": label,
        "ProgramArguments": program_arguments,
        "WorkingDirectory": str(Path.home()),
        "RunAtLoad": True,
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": str(log_dir / "health.out.log"),
        "StandardErrorPath": str(log_dir / "health.err.log"),
    }
    return plistlib.dumps(payload, sort_keys=False)


def install_health_agent(
    *,
    label: str = DEFAULT_LABEL,
    daily_at: str = "16:45",
    port: int = 8451,
    notify: bool = True,
    plist_dir: Path = DEFAULT_PLIST_DIR,
    load: bool = False,
) -> Path:
    plist_dir.mkdir(parents=True, exist_ok=True)
    log_dir = DEFAULT_LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / f"{label}.plist"
    plist_path.write_bytes(
        build_health_agent_plist(
            label=label,
            python_path=Path(sys.executable).resolve(),
            daily_at=daily_at,
            port=port,
            log_dir=log_dir,
            notify=notify,
        )
    )
    if load:
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
        subprocess.run(["launchctl", "load", str(plist_path)], check=True)
    return plist_path


def uninstall_health_agent(label: str = DEFAULT_LABEL, plist_dir: Path = DEFAULT_PLIST_DIR) -> Path:
    plist_path = plist_dir / f"{label}.plist"
    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], check=False, capture_output=True)
        plist_path.unlink()
    return plist_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install the Treasury dashboard macOS health checker")
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--daily-at", default="16:45")
    parser.add_argument("--port", type=int, default=8451)
    parser.add_argument("--load", action="store_true", help="Load the LaunchAgent immediately after writing it")
    parser.add_argument("--no-notify", action="store_true", help="Log failures without macOS notifications")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    if args.uninstall:
        plist_path = uninstall_health_agent(label=args.label)
        print(f"Removed {plist_path}")
        return 0

    plist_path = install_health_agent(
        label=args.label,
        daily_at=args.daily_at,
        port=args.port,
        notify=not args.no_notify,
        load=args.load,
    )
    print(f"Wrote {plist_path}")
    if args.load:
        print(f"Loaded {args.label}; health will be checked daily at {args.daily_at}")
    else:
        print(f"Load with: launchctl load {plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
