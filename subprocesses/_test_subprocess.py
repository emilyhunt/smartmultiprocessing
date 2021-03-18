"""A test subprocess! Executes for as long as you'd like."""
import time

from ..utilities import Logfile


def test_waiter(logger: Logfile, wait_time: int):
    logger("Starting test_waiter function")
    logger(f"Waiting for {wait_time} seconds")

    time.sleep(wait_time)

    logger("Waiting completed!")
