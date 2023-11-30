import time


def sleeper(sleep=1):
    time.sleep(sleep)

def crasher():
    raise ValueError("Test error =)")

def returner(value_to_return, sleep=0):
    time.sleep(sleep)
    return value_to_return

def allocator(size_to_allocate, sleep=0):
    my_array
    time.sleep(sleep)