import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from documenttools.engines import WORKER_FLAG
from documenttools.office_worker import main as office_worker_main


def _run_worker_if_requested() -> bool:
    """Dispatch the hidden COM helper mode before any GUI is created."""
    arguments = sys.argv[1:]
    if not arguments or arguments[0] != WORKER_FLAG:
        return False
    return True


if __name__ == "__main__":
    if _run_worker_if_requested():
        raise SystemExit(office_worker_main(sys.argv[2:]))

    from documenttools.app import run

    run()
