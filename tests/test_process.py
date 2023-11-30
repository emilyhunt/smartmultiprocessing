import time

import psutil
import multiprocessing
from smartmultiprocessing import SmartProcess
from smartmultiprocessing.errors import NoResultError, ProcessFailedError, ProcessStillRunningError
from smartmultiprocessing.process import pipe_return_function
from tests.functions import sleeper, crasher, returner, allocator, cpu_user, childer
import pytest


def wait_until_children(process, wait_time=1):
    start_time = time.time()
    children = []
    while time.time() < start_time + wait_time and len(children) == 0:
        children = process.get_children()
    if len(children) == 0:
        raise RuntimeError("Unable to get child processes.")
    return children


def test_testing_functions():
    """Simple integration test for testing functions that checks that they run.

    If this function fails, then all tests in the module are liable to be inaccurate.
    """
    sleeper(0.1)
    with pytest.raises(RuntimeError):
        crasher()
    assert returner(1) == 1
    result = returner(1, kwarg_to_return="test")
    assert result[0] == 1
    assert result[1] == "test"
    allocator(100)
    cpu_user(0.1)
    assert childer(0.1) == 0


def test_pipe_return_function():
    """Checks that pipe_return_function can return a result."""
    result_pipe, send_pipe = multiprocessing.Pipe(duplex=False)

    pipe_return_function(send_pipe, returner, 5, kwarg_to_return="val2")
    assert result_pipe.poll(timeout=1)
    result = result_pipe.recv()
    assert result is not None
    assert len(result) == 2
    assert result[0] == 5
    assert result[1] == "val2"


def test_SmartProcess_typical_use():
    """Tests running a simple process within a SmartProcess."""
    process = SmartProcess(target=returner, args=(0,))
    process.start()
    process.join()


def test_SmartProcess_terminate():
    """Tests our ability to terminate a process."""
    # Without children
    process = SmartProcess(target=sleeper, args=(5,))
    process.start()
    assert process.is_alive()
    process.terminate(children=False)
    time.sleep(0.01)  # Necessary for multiprocessing to sort its life out
    assert process.get_exitcode() == -15
    assert process.is_alive() is False

    # With children
    process = SmartProcess(target=childer, args=(5,))
    process.start()
    assert process.is_alive()

    # Try to get children for upto a second
    children = wait_until_children(process)
    assert len(children) == 1
    assert psutil.pid_exists(children[0].pid)

    process.terminate(children=True)
    time.sleep(0.01)  # Necessary for multiprocessing to sort its life out
    assert process.is_alive() is False
    assert psutil.pid_exists(children[0].pid) is False


def test_SmartProcess_kill():
    """Tests our ability to kill a process."""
    # Without children
    process = SmartProcess(target=sleeper, args=(5,))
    process.start()
    assert process.is_alive()
    process.kill(children=False)
    time.sleep(0.01)  # Necessary for multiprocessing to sort its life out
    assert process.get_exitcode() == -9
    assert process.is_alive() is False

    # With children
    process = SmartProcess(target=childer, args=(5,))
    process.start()
    assert process.is_alive()

    # Try to get children for upto a second
    children = wait_until_children(process)
    assert len(children) == 1
    assert psutil.pid_exists(children[0].pid)

    process.kill(children=True)
    time.sleep(0.01)  # Necessary for multiprocessing to sort its life out
    assert process.is_alive() is False
    assert psutil.pid_exists(children[0].pid) is False


def test_SmartProcess_get_children():
    """Tests our ability to get children of a process."""
    process = SmartProcess(target=childer, args=(5,))
    process.start()

    # Try to get children for upto a second
    children = wait_until_children(process)
    assert len(children) == 1
    assert psutil.pid_exists(children[0].pid)

    process.terminate(children=True)


def test_SmartProcess_get_result():
    """Tests our ability to fetch a result from a process."""
    # Test that it raises an error if the process hasn't finished
    process = SmartProcess(target=sleeper, args=(5,), fetch_result=True)
    process.start()
    with pytest.raises(ProcessStillRunningError):
        process.get_result()
    process.kill()

    # Test that we get an error on a crash
    process = SmartProcess(target=crasher, fetch_result=True)
    process.start()
    with pytest.raises(ProcessFailedError):
        process.get_result(join=True)
    try:
        process.kill()
    except psutil.NoSuchProcess:
        pass

    # Test that we can get a result!
    process = SmartProcess(
        target=returner,
        args=("val1",),
        kwargs=dict(kwarg_to_return=["val2", 5]),
        fetch_result=True,
    )
    process.start()
    result = process.get_result(join=True)
    assert process.get_exitcode() == 0
    assert result is not None
    assert len(result) == 2
    assert result[0] == "val1"
    assert result[1] == ["val2", 5]

    # Test that the pipe is empty now
    with pytest.raises(NoResultError):
        process.get_result(pipe_timeout=0.1)  # No timeout as we don't need to wait


# if __name__ == "__main__":
#     process = SmartProcess(
#         target=returner,
#         args=("val1",),
#         kwargs=dict(kwarg_to_return=["val2", 5]),
#         fetch_result=True,
#     )
#     process.start()
#     process.join()
