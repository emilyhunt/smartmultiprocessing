"""A suite of simple functions for use in testing the module."""
import time
import random
from multiprocessing import Process


def sleeper(sleep=1):
    time.sleep(sleep)

def crasher():
    raise RuntimeError("Test error =)")

def returner(value_to_return, kwarg_to_return=None, sleep=0):
    time.sleep(sleep)
    if kwarg_to_return is None:
        return value_to_return
    else:
        return (value_to_return, kwarg_to_return)

def allocator(size_to_allocate, sleep=0):
    my_array = bytearray(size_to_allocate)
    time.sleep(sleep)
    return my_array

def cpu_user(time_to_use=1):
    start_time = time.time()
    while time.time() < start_time + time_to_use:
        [random.random() for i in range(1000)]

def childer(sleep=1):
    process = Process(target=sleeper, args=(sleep,))
    process.start()
    process.join()
    return process.exitcode