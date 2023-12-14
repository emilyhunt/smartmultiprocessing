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
    """Extension to `multiprocessing.Process` with multiple memory-management
    options, the ability to return results from processes, and more.

    This is a relatively low-level part of SmartMultiprocessing. Average users are
    probably more interested in more abstract parts of this library, like 
    `SmartPool` and `SmartQueue`, which can initialise as many `SmartProcess`es as you'd
    like and include GUI options.

    The API of `SmartProcess` matches that of `multiprocessing.Process`, except with
    some notable additions like:

    `SmartProcess.resource_usage()` - get the process' current CPU and memory usage.
    
    `SmartProcess.is_finished()` - boolean for if process is done.

    `SmartProcess.get_result()` - get the result from `target`, if process finished.

    `SmartProcess.get_children()` - get all child processes of this process.
    """
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
        """Create a new SmartProcess object.

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
        0
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
        """Gets the children of the process. TODO: document params
        """
        return self.psutil_process.children(recursive=recursive)

    def memory_usage(self, children: Union[Iterable, bool] = False) -> int:
        """Returns current memory usage of the process.. TODO: document params"""
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
        """Returns current CPU usage of the process.. TODO: document params"""
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
        """Returns a dict of CPU and memory usage of the process.. TODO: document"""
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
        """Attempts to fetch a result for the process. TODO: document params"""
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
        """Returns the exitcode of the process, which is only set if it has finished."""
        return self.process.exitcode

    def run(self):
        """Runs the target of the process. 
        
        Not recommended: use `SmartProcess.start()` instead.
        """
        self.process.run()

    def start(self):
        """Starts the process."""
        self.process.start()
        self.psutil_process = psutil.Process(self.process.pid)

    def join(self, timeout: Optional[float] = None):
        """Joins the thread of the process (assuming it has been started already) and
        blocks until completion.
        """
        self.process.join(timeout)

    def is_alive(self) -> bool:
        """Boolean of whether or not the process is currently running."""
        return self.process.is_alive()

    def is_finished(self) -> bool:
        """Boolean of whether or not the process has finished."""
        if self.is_alive():
            return False
        if exitcode := self.get_exitcode() != 0:
            raise ProcessFailedError(
                f"Process failed during execution with exitcode {exitcode}"
            )
        return True

    def terminate(self, children=True):
        """Sends a SIGTERM and terminates the process. TODO: document params"""
        children = self._children_in_arg(children)
        self.process.terminate()
        for a_child in children:
            try:
                a_child.terminate()
            except psutil.NoSuchProcess:
                pass

    def kill(self, children=True):
        """Sends a SIGKILL and kills the process. TODO: document params"""
        children = self._children_in_arg(children)
        self.process.kill()
        for a_child in children:
            try:
                a_child.kill()
            except psutil.NoSuchProcess:
                pass

    def close(self):
        """Closes all resources occupied by the process."""
        self.process.close()
