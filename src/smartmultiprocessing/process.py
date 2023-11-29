"""Definition of the SmartProcess class, which extends multiprocessing.Process to include memory monitoring."""
import multiprocessing
import psutil
import time
from typing import Optional, Iterable, Any, Mapping, Union


class SmartProcess:
    def __init__(
        self,
        target=None,
        name: Optional[str] = None,
        args: Iterable[Any] = (),
        kwargs: Mapping[str, Any] = {},
        group: None = None,
        daemon: Optional[bool] = None,
    ) -> None:
        self.process = multiprocessing.Process(
            group=group,
            target=target,
            name=name,
            args=args,
            kwargs=kwargs,
            daemon=daemon,
        )
        self.psutil_process = None

    def _get_children(self):
        return self.psutil_process.children(recursive=True)

    def memory_usage(self, children: Union[Iterable, bool] = False) -> int:
        # Proportional set size of parent thread. Best guess at the memory usage of this
        # thread, as shared with others.
        memory_usage = self.psutil_process.memory_full_info().pss
        if not children:
            return memory_usage

        # Optionally also get the memory usage of all child processes of this process.
        if children == True:
            children = self._get_children()
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

        for child_process in children:
            try:
                cpu_percent += child_process.cpu_percent(interval=None)
            except psutil.NoSuchProcess:
                pass

        if interval is None:
            return cpu_percent

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
