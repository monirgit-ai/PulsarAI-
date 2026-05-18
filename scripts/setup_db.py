#!/usr/bin/env python3
"""Run Alembic migrations against DATABASE_URL from .env."""

import subprocess
import sys


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
