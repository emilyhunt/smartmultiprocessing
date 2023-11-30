from smartmultiprocessing import SmartProcess
from .functions import sleeper, crasher, returner, allocator, cpu_user
import pytest

def test_testing_functions():
    """Simple integration test for testing functions that checks that they run.
    
    If this function fails, then all tests in the module are liable to be inaccurate.
    """
    sleeper(0.1)
    with pytest.raises(RuntimeError):
        crasher()
    assert returner(1) == 1
    allocator(100)
    cpu_user(0.1)

