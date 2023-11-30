"""SmartProcess class - extends multiprocessing.Process to include memory monitoring."""
import multiprocessing
import psutil
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
        

class SmartProcess:
    def __init__(
        self,
        target: Callable = None,
        name: Optional[str] = None,
        args: Iterable[Any] = (),
        kwargs: Mapping[str, Any] = {},
        group: None = None,
        daemon: Optional[bool] = None,
        fetch_result: bool = False,
    ) -> None:
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

    def get_children(self, recursive: bool = True):
        return self.psutil_process.children(recursive=recursive)

    def memory_usage(self, children: Union[Iterable, bool] = False) -> int:
        # Proportional set size of parent thread. Best guess at the memory usage of this
        # thread, as shared with others.
        memory_usage = self.psutil_process.memory_full_info().pss
        if not children:
            return memory_usage

        # Optionally also get the memory usage of all child processes of this process.
        if children is True:
            children = self.get_children()
        for child_process in children:
            try:
                memory_usage += child_process.memory_info().rss
            except psutil.NoSuchProcess:
                pass
        return memory_usage

    def cpu_usage(
        self,
        interval: Optional[Union[int, float]] = None,
        children: Union[Iterable, bool] = False,
    ) -> int:
        if not children:
            return self.psutil_process.cpu_percent(interval=interval)
        cpu_percent = self.psutil_process.cpu_percent(interval=None)

        if children is True:
            children = self.get_children()
        for child_process in children:
            try:
                cpu_percent += child_process.cpu_percent(interval=None)
            except psutil.NoSuchProcess:
                pass

        if interval is None:
            return cpu_percent
        
    def get_result(self, timeout: Optional[float] = None):
        if not self.fetch_result:
            raise ValueError(
                "get_result not set during initialisation! No result is expected from"
                " running of this function."
            )
        if timeout is not None:
            self.process.join(timeout)
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

    def terminate(self):
        self.process.terminate()

    def kill(self):
        self.process.kill()

    def close(self):
        self.process.close()
