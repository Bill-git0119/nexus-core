"""
Nexus System — Main Orchestrator
Runs all agents in sequence: Scout → Critic → Monetizer → Architect
Designed for 24/7 automation via cron / Task Scheduler.
"""

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging setup — logs to both console and logs/ directory
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)

log_file = LOG_DIR / f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ],
)
logger = logging.getLogger("nexus")

# ---------------------------------------------------------------------------
# Agent imports
# ---------------------------------------------------------------------------
sys.path.insert(0, str(PROJECT_ROOT / "agents"))

from scout import run as run_scout
from critic import run as run_critic
from monetizer import run as run_monetizer
from architect import run as run_architect

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
AGENTS = [
    ("Scout", run_scout),
    ("Critic", run_critic),
    ("Monetizer", run_monetizer),
    ("Architect", run_architect),
]


def main() -> None:
    start = time.time()
    logger.info("=" * 60)
    logger.info("Nexus System — Pipeline started")
    logger.info("=" * 60)

    for name, run_fn in AGENTS:
        logger.info(f"--- [{name}] Starting ---")
        step_start = time.time()
        try:
            result = run_fn()
            elapsed = time.time() - step_start
            logger.info(f"--- [{name}] Completed in {elapsed:.1f}s → {result}")
        except SystemExit as e:
            if e.code == 0:
                logger.info(f"--- [{name}] Exited cleanly (nothing to process)")
                break
            logger.error(f"--- [{name}] Failed with exit code {e.code}")
            sys.exit(e.code)
        except Exception:
            logger.exception(f"--- [{name}] Unhandled exception ---")
            sys.exit(1)

    total = time.time() - start
    logger.info("=" * 60)
    logger.info(f"Nexus System — Pipeline finished in {total:.1f}s")
    logger.info(f"Log saved to {log_file}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
