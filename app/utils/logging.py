"""Single logging entry point, so every module logs the same way."""

import logging
import os
import sys

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(levelname)-7s %(name)-22s %(message)s",
    stream=sys.stderr,
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
