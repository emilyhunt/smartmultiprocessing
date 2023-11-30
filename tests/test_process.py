import time

import psutil
from smartmultiprocessing import SmartProcess
from smartmultiprocessing.process import ReturnableFunctionWrapper
from .functions import sleeper, crasher, returner, allocator, cpu_user, childer
import pytest


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


def test_ReturnableFunctionWrapper():
    """Checks that ReturnableFunctionWrapper can return a result."""
    func = ReturnableFunctionWrapper(returner)

    # Check that there's no result before running
    assert func.get_result() is None

    # Run & check result
    func(1, kwarg_to_return="test")
    result = func.get_result()
    assert result is not None
    assert len(result) == 2
    assert result[0] == 1
    assert result[1] == "test"


def test_SmartProcess_typical_use():
    """Tests running a simple process within a SmartProcess."""
    process = SmartProcess(target=returner, args=(0,))
    process.start()
    process.join()


def wait_until_children(process, wait_time=1):
    """Convenience function for waiting until child processes have started."""
    start_time = time.time()
    children = []
    while time.time() < start_time + wait_time and len(children) == 0:
        children = process.get_children()
    if len(children) == 0:
        raise RuntimeError("Unable to get child processes.")
    return children


def test_SmartProcess_terminate():
    """Tests our ability to terminate a process."""
    # Without children
    process = SmartProcess(target=sleeper, args=(60,))
    process.start()
    assert process.is_alive()
    process.terminate(children=False)
    time.sleep(0.01)  # Necessary for multiprocessing to sort its life out
    assert process.get_exitcode() == -15
    assert process.is_alive() is False

    # With children
    process = SmartProcess(target=childer, args=(60,))
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
    process = SmartProcess(target=sleeper, args=(60,))
    process.start()
    assert process.is_alive()
    process.kill(children=False)
    time.sleep(0.01)  # Necessary for multiprocessing to sort its life out
    assert process.get_exitcode() == -9
    assert process.is_alive() is False

    # With children
    process = SmartProcess(target=childer, args=(60,))
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
    process = SmartProcess(target=childer, args=(60,))
    process.start()

    # Try to get children for upto a second
    children = wait_until_children(process)
    assert len(children) == 1
    assert psutil.pid_exists(children[0].pid)

    process.terminate(children=True)


def test_SmartProcess_get_result():
    """Tests our ability to fetch a result from a process."""
    # Test that it raises an error if the process hasn't finished
    process = SmartProcess(target=sleeper, args=(60,),)
    process.start()
    with pytest.raises(RuntimeError):
        process.get_result()
    process.kill()

    # Test that we get an error on a crash
    process = SmartProcess(target=sleeper, args=(60,),)
    process.start()
    with pytest.raises(RuntimeError):
        process.get_result()
    process.kill()


    process = SmartProcess(
        target=sleeper, args=("val1",), kwargs=dict(kwarg_to_return="val2", sleep=60)
    )
