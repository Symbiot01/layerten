"""Entry point: python -m layerten.merge"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from layerten.merge.runner import run_merge

run_merge()
