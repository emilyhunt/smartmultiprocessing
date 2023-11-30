"""SmartProcess class - extends multiprocessing.Process to include memory monitoring."""
import multiprocessing
import psutil
import time
from typing import Optional, Iterable, Any, Mapping, Union, Callable


class ReturnableFunctionWrapper:
    def __init__(self, target: Callable):
        """Intended for use with a SmartProcess. Wraps a target function and makes
        it send its result to a pipe.
        """
        self.result_pipe, self.send_pipe = multiprocessing.Pipe(duplex=False)
        self.target = target

    def get_result(self) -> Any:
        if self.result_pipe.poll():
            return self.result_pipe.recv()
        else:
            return None

    def __call__(self, *args: Any, **kwargs: Any):
        result = self.target(*args, **kwargs)
        self.send_pipe.send(result)


def if_exists_cpu_percent(process: psutil.Process, interval):
    """Safely tries to get CPU usage of a psutil.Process. Returns zero if process 
    doesn't exist.
    """
    try:
        return process.cpu_percent(interval)
    except psutil.NoSuchProcess:
        return 0
    

def if_exists_memory_pss(process: psutil.Process):
    try:
        return process.memory_full_info().pss
    except psutil.NoSuchProcess:
        return 0
    

def if_exists_memory_rss(process: psutil.Process):
    try:
        return process.memory_info().rss
    except psutil.NoSuchProcess:
        return 0



class SmartProcess:
    def __init__(
        self,
        group: None = None,
        target: Callable = None,
        name: Optional[str] = None,
        args: Iterable[Any] = (),
        kwargs: Mapping[str, Any] = {},
        daemon: Optional[bool] = None,
        fetch_result: bool = False,
    ) -> None:
        if group is not None:
            raise NotImplementedError(
                "group must always be None. This argument is reserved due to future "
                "compatibility with thread groups in the Threading module."
            )

        self.fetch_result = fetch_result
        if fetch_result:
            self.target = ReturnableFunctionWrapper(target=target)
        else:
            self.target = target

        self.process = multiprocessing.Process(
            group=group,
            target=target,
            name=name,
            args=args,
            kwargs=kwargs,
            daemon=daemon,
        )
        self.psutil_process = None

    def _children_in_arg(self, children: Union[Iterable, bool]):
        if False:
            return tuple()
        if True:
            return self.get_children()
        return children

    def get_children(self, recursive: bool = True):
        return self.psutil_process.children(recursive=recursive)

    def memory_usage(self, children: Union[Iterable, bool] = False) -> int:
        # Proportional set size of parent thread. Best guess at the memory usage of this
        # thread, as shared with others.
        memory_usage = if_exists_memory_pss(self.psutil_process)
        if not children:
            return memory_usage

        # Optionally also get the memory usage of all child processes of this process.
        children = self._children_in_arg(children)
        for child_process in children:
            memory_usage += if_exists_memory_rss(child_process)
        return memory_usage

    def cpu_usage(
        self,
        interval: Optional[Union[int, float]] = None,
        children: Union[Iterable, bool] = False,
    ) -> int:
        if not children:
            return if_exists_cpu_percent(self.psutil_process, interval)
        children = self._children_in_arg(children)

        # If there are children, we should do a first pass on everything
        cpu_percent = if_exists_cpu_percent(self.psutil_process, None)
        for child_process in children:
            cpu_percent += if_exists_cpu_percent(child_process, None)
        if interval is None:
            return cpu_percent
        
        # If an interval is requested, we sleep and do a pass again
        time.sleep(interval)
        cpu_percent = if_exists_cpu_percent(self.psutil_process, None)
        for child_process in children:
            cpu_percent += if_exists_cpu_percent(child_process, None)
        return cpu_percent

    def get_result(self, timeout: Optional[float] = None):
        if not self.fetch_result:
            raise ValueError(
                "get_result not set during initialisation! No result is expected from"
                " running of this function."
            )
        if timeout is not None:
            self.process.join(timeout)
        if self.get_exitcode() is None:
            raise RuntimeError("Process has not yet finished! Unable to get result.")
        if self.get_exitcode() != 0:
            raise RuntimeError("Process failed! Unable to get result.")
        return self.target.get_result()

    def get_exitcode(self):
        return self.process.exitcode

    def run(self):
        self.process.run()

    def start(self):
        self.process.start()
        self.psutil_process = psutil.Process(self.process.pid)

    def join(self, timeout: Optional[float] = None):
        self.process.join(timeout)

    def is_alive(self) -> bool:
        return self.process.is_alive()

    def terminate(self, children=True):
        children = self._children_in_arg(children)
        self.process.terminate()
        for a_child in children:
            try:
                a_child.terminate()
            except psutil.NoSuchProcess:
                pass

    def kill(self, children=True):
        children = self._children_in_arg(children)
        self.process.kill()
        for a_child in children:
            try:
                a_child.kill()
            except psutil.NoSuchProcess:
                pass

    def close(self):
        self.process.close()
