"""A test subprocess! Executes for as long as you'd like."""
import time
import numpy as np

from ..utilities import Logfile


def test_waiter(logger: Logfile, wait_time: int):
    logger("Starting test_waiter function")
    logger(f"Waiting for {wait_time} seconds")

    time.sleep(wait_time)

    logger("Waiting completed!")


def test_memory_waiter(logger: Logfile, wait_time: int, memory_scaling_factor=0.1):
    logger("Starting test_memory_waiter function")

    target_memory_usage = wait_time * memory_scaling_factor
    logger(f"Allocating memory of size wait_time * factor GB! ({target_memory_usage:.2f} GB)")

    # Initialise an array of size in memory target_memory_usage in bytes (each element takes up 8 bytes)
    x = np.zeros(int(target_memory_usage * 1024**3 / 8))

    logger(f"Waiting for {wait_time} seconds")

    time.sleep(wait_time)

    # Do something to x later just so that re-allocation is impossible
    x += 1

    logger("Waiting completed!")
