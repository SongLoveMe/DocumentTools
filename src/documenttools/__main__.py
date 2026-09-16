"""Package entry point supporting ``python -m documenttools``."""

from __future__ import annotations

import sys

from .engines import WORKER_FLAG


def main() -> int:
    arguments = sys.argv[1:]
    if arguments and arguments[0] == WORKER_FLAG:
        from .office_worker import main as office_worker_main

        return office_worker_main(arguments[1:])

    from .app import run

    return run()


raise SystemExit(main())
