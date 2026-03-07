"""Entry point: python -m layerten.sort"""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from layerten.sort.timeline import run_sort

run_sort()
