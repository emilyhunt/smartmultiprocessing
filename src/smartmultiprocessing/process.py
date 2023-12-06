"""SmartProcess class - extends multiprocessing.Process to include memory monitoring."""
import multiprocessing
from multiprocessing.connection import Connection
import psutil
import time
from typing import Optional, Iterable, Any, Mapping, Union, Callable
from .errors import ProcessFailedError, ProcessStillRunningError, NoResultError


def pipe_return_function(pipe: Connection, target, *args, **kwargs):
    """Returns result from `target` by sending it down a multiprocessing.Pipe
    connection.
    """
    result = target(*args, **kwargs)
    pipe.send(result)


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
        """Extension to `multiprocessing.Process` with multiple memory-management
        options, the ability to return results from processes, and more.

        The API of `SmartProcess` matches that of `multiprocessing.Process`, except with
        some notable additions like:

        SmartProcess.resource_usage() - get the process' current CPU and memory usage
        SmartProcess.is_finished() - boolean for if process is done
        SmartProcess.get_result() - get the result from `target`, if process finished
        SmartProcess.get_children() - get all child processes of this process.

        Parameters
        ----------
        group : None
            Argument that must always be None. It exists for compatibility with the
            threading.Thread API.
        target : Callable
            Target function to run on.
        name : str, optional
            Name of process to pass to multiprocessing.Process.
        args : Iterable[Any], optional
            Arguments to pass to `target`.
        kwargs : Mappable[str, Any], optional
            Keyword arguments to pass to `target`.
        daemon : None or bool, optional
            Whether or not to run as a daemon (background process). Passed to
            multiprocessing.Process. TODO: not sure if this can actually be supported...
        fetch_result: bool, default = False
            Whether or not to try and fetch a result in-memory for `target`. `target`
            must return a value for this to be used.

        Notes
        -----
        CPU and memory usage tracking is done using `psutil`. Support on systems that
        aren't Linux, Mac, or Windows may be limited.

        Examples
        --------
        Start a process that prints to the console in the background:

        >>> p = smartmultiprocessing.SmartProcess(target=lambda: print("Hello World"))

        >>> p.start()
        Hello World

        We can check if the process is finished:

        >>> p.is_finished()
        True

        or get its exitcode:

        >>> p.get_exitcode()
        True
        """
        if group is not None:
            raise NotImplementedError(
                "group must always be None. This argument is reserved due to future "
                "compatibility with thread groups in the Threading module."
            )

        # Setup optional returning of function result
        self.fetch_result = fetch_result
        self.result_pipe = None
        if fetch_result:
            self.result_pipe, send_pipe = multiprocessing.Pipe(duplex=False)
            args = [send_pipe, target] + list(args)
            target = pipe_return_function

        # Initialise underlying process
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
        if children is False:
            return tuple()
        if children is True:
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

    def resource_usage(
        self,
        interval: Optional[Union[int, float]] = None,
        children: Union[Iterable, bool] = False,
    ) -> Mapping[str, Union[int, float]]:
        children = self._children_in_arg(children)
        return {
            "cpu_usage": self.cpu_usage(interval=interval, children=children),
            "memory_usage": self.memory_usage(children=children),
        }

    def get_result(
        self,
        join: bool = False,
        timeout: Optional[float] = None,
        pipe_timeout: Optional[float] = 1.0,
    ):
        if not self.fetch_result:
            raise ValueError(
                "get_result not set during initialisation! No result is expected from"
                " running of this function."
            )
        if join:
            self.process.join(timeout)
        if not self.is_finished():
            raise ProcessStillRunningError(
                "Process has not yet finished! Unable to get result."
            )
        if not self.result_pipe.poll(pipe_timeout):
            raise NoResultError(
                "Process did not return a result after completion, or result was "
                "already accessed, or pipe_timeout was too short."
            )
        try:
            return self.result_pipe.recv()
        except EOFError:
            raise NoResultError(
                "Pipe contains no result, or other end of pipe was already closed."
            )

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

    def is_finished(self) -> bool:
        if self.is_alive():
            return False
        if exitcode := self.get_exitcode() != 0:
            raise ProcessFailedError(
                f"Process failed during execution with exitcode {exitcode}"
            )
        return True

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
