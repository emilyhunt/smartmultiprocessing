"""Definition of the main class of the module."""

import numpy as np
import pandas as pd
import curses
import time
import datetime
import multiprocessing
import psutil
import matplotlib.pyplot as plt
import sys
import warnings

from .utilities import timestamp, Logfile
from typing import Optional
from scipy.interpolate import LSQUnivariateSpline
from _curses import error as CursesError


SIX_SIX_SIX_THE_DEVILS_DATE = datetime.datetime(year=6666, month=6, day=6, hour=6, minute=6, second=6)


class SubprocessHandler:

    def __init__(self, config: dict):
        """The SubprocessHandler is an advanced but lightweight class for distributed running of tasks on multiple
        cores.

        Parameters
        ----------
        config : dict
            The configuration of the handler. It should follow a standard format.
            Todo: update this fstring as I code more

        """
        self.config = config
        self.config['logging_dir'].mkdir(exist_ok=True, parents=True)
        self._main_logfile = Logfile(self.config['logging_dir'] / f"main {timestamp(trailing_space=False)}.log")

        self._main_logfile("Initialising SubprocessHandler...", send_to_print=True)

        # Storage space for processes themselves
        self.current_task_assignments = np.full(self.config['max_threads'], -1)  # Array indicating target index of each
        self.default_process_dict = {'update': '-', 'process': None,
                                     'fuck_you_pycharm': Optional[multiprocessing.Process]}
        self.processes = [self.default_process_dict.copy() for i in range(self.config['max_threads'])]

        if self.config['benchmarking_tasks'] > 0:
            self.current_max_threads = 1
        else:
            self.current_max_threads = self.config['target_threads']

        # Some numbers on current tasks
        self.tasks_total = len(config['args'])
        self.tasks_completed = 0
        self.last_task_count_when_we_fitted = 0
        self.last_task_count_when_we_plotted = 0

        # Generate a more sophisticated dataframe of task info storage
        self._sampling_time = 1 * self.config['main_thread_sleep_time']  # Needed for fits
        self.task_information, self.completed_tasks_csv_file, self.write_header = None, None, None
        self._generate_task_info_dataframe()

        # Display settings
        self.padding = len(str(self.config['max_threads']))
        self._last_window_size = (24, 24)
        self._keypress_info = ["", ""]
        self._current_input = ""
        self._config_to_change = None

        # Resource tracking space
        self.process_cpu_usage = np.zeros(self.config['max_threads'])
        self.process_memory_usage = np.zeros(self.config['max_threads'])
        self.total_cpu_usage = 0.0
        self.total_memory_usage = 0.0
        self.expected_memory_usage = 0.0
        self.expected_finish_time = SIX_SIX_SIX_THE_DEVILS_DATE  # lol
        self.step = 0

        # Fits for the stuff
        self._fit_time = None
        self._fit_memory = None
        self._have_done_a_fit = False

        self._main_logfile("Initialisation complete!", send_to_print=True)

        # Compatibility - the current Python version controls whether or not we can use the Process.kill() method
        if sys.version_info.major == 2:
            raise RuntimeError("Why are you still using Python 2? Ask yourself, honestly: why?")
        elif sys.version_info.major == 3 and sys.version_info.minor < 7:
            warnings.warn(FutureWarning("You are currently using a Python version below 3.7 and will not have access "
                                        "to more effective multithreading memory crisis management. If your target "
                                        "function creates child processes then these cannot be killed in the event "
                                        "of overmemory protection, which may cause overmemory protection to be "
                                        "ineffective. Consider upgrading!"))
            self._greater_than_python_3_6 = False
        else:
            self._greater_than_python_3_6 = True

    def _generate_task_info_dataframe(self):
        """Generates a task info dataframe in the initial startup of the program."""
        self._main_logfile("Generating initial task info dataframe...", send_to_print=True)
        # Look for an existing df
        completed_tasks_log = self.config['logging_dir'] / f"{self.config['run_name']}_completed_tasks.csv"
        if completed_tasks_log.exists():
            existing_task_information = pd.read_csv(completed_tasks_log)
            existing_task_information['in_progress'] = False  # duh,,, we just started
            completed_tasks = existing_task_information['args'].to_numpy()
            write_header = False
        else:
            existing_task_information = None
            completed_tasks = np.zeros(0, dtype=np.int)
            write_header = True

        # Generate a blank df with every task to run on, ignoring tasks that are already done
        not_completed = np.isin(self.config['args'], completed_tasks, invert=True)

        n_not_completed = np.count_nonzero(not_completed)
        if n_not_completed == 0:
            raise RuntimeError("no uncompleted tasks found! It looks like this job has already been done (or like "
                               "something has gone wrong. Are there actually any tasks in your config?)")

        task_information = pd.DataFrame({
            'args': self.config['args'][not_completed],
            'metadata': self.config['metadata'][not_completed],
            'runtime': -1.0,
            'memory': -1.0,
            'expected_runtime': 0.0,
            'expected_memory': self.config['pre_benchmark_expected_memory'],
            'start_time': 0.0,
            'completion_time': 0,
            'in_progress': False,
            'remaining_to_do': True,
        })

        # If there was indeed existing information, then we can add this and also do a little fit
        if existing_task_information is not None:
            task_information = pd.concat([existing_task_information, task_information], ignore_index=True)
            self.tasks_completed = np.count_nonzero(np.invert(task_information['remaining_to_do']))
            self.last_task_count_when_we_plotted = self.tasks_completed
            self._main_logfile(f"  found {self.tasks_completed} already completed tasks!", send_to_print=True)

        self.task_information = task_information
        self.completed_tasks_csv_file = completed_tasks_log
        self.write_header = write_header

        # We can also do a little fit if there were in fact some tasks that got done before!
        if existing_task_information is not None:
            self._fit_resource_usage()

    def _update_task_info_dataframe_on_disk(self, indexes_to_write):
        """Appends a line or lines to the task info dataframe. Will write a header if the file didn't exist before."""
        lines_to_append = self.task_information.loc[np.atleast_1d(indexes_to_write)]
        lines_to_append.to_csv(self.completed_tasks_csv_file, index=False, mode='a', header=self.write_header)
        self.write_header = False

    def _check_memory_usage(self):
        """Monitors the memory usage of the respective subprocesses and code. In the event of a memory limit being
        reached, this function will kill the lowest priority processes."""
        # Cycle over all processes, using psutil to get their total cpu and memory usages
        self.process_cpu_usage = np.zeros(self.config['max_threads'])
        self.process_memory_usage = np.zeros(self.config['max_threads'])

        running_processes = (self.current_task_assignments != -1).nonzero()[0]
        for i in running_processes:
            try:
                self.process_cpu_usage[i] = self.processes[i]['psutil_process'].cpu_percent()
                self.process_memory_usage[i] = self.processes[i]['psutil_process'].memory_info().rss / 1024**3
            except psutil.NoSuchProcess:
                self.process_cpu_usage[i] = self.process_memory_usage[i] = 0.0

        self.total_cpu_usage = np.sum(self.process_cpu_usage)
        self.total_memory_usage = np.sum(self.process_memory_usage)

        # Update the dataframe of task info
        running_tasks = self.current_task_assignments[running_processes]
        new_memory_is_higher = (
                self.process_memory_usage[running_processes] > self.task_information.loc[running_tasks, 'memory'])

        self.task_information.loc[running_tasks[new_memory_is_higher], 'memory'] = (
            self.process_memory_usage[running_processes[new_memory_is_higher]])

        # Do something if the memory usage is over our tolerance
        if self.total_memory_usage > self.config['max_memory_hard_limit']:

            # We can deal with this by either raising an error...
            if self.config['overmemory_raise_error']:
                raise RuntimeError("process has encountered an overmemory event and had to close! Last measursed at "
                                   f"{self.total_memory_usage} GB of RAM.")

            # ... or by finding processes to kill based on their age. We'll kill processes until the total memory usage
            # is small enough. We kill the youngest processes first ("the younglings, AnakinSkywalker.py") as they've
            # had the lowest CPU time investment so far.
            else:

                self._main_logfile("MEMORY HARD LIMIT EXCEEDED")

                # Some info for an informative error message if this doesn't work
                previous_running_tasks = self.current_task_assignments[running_processes].copy()
                previous_memory_usages = self.process_memory_usage[running_processes].copy()

                # Cycle, deleting 1 process at a time until we're ok
                n_running_processes = len(running_processes)
                while self.total_memory_usage > self.config['max_memory']:
                    index_of_task_to_kill = self.task_information.loc[running_tasks, 'start_time'].idxmax()
                    index_of_process_to_kill = (self.current_task_assignments == index_of_task_to_kill).nonzero()[0][0]

                    self.total_memory_usage -= self.process_memory_usage[index_of_process_to_kill]

                    self._kill_subprocess(
                        index_of_process_to_kill,
                        f"KILLED due to overmemory: task {previous_running_tasks[index_of_process_to_kill]} with "
                        f"{previous_memory_usages[index_of_process_to_kill]:.3f} GB memory last"
                    )

                    running_processes = (self.current_task_assignments != -1).nonzero()[0]
                    running_tasks = self.current_task_assignments[running_processes]
                    n_running_processes = len(running_processes)

                    # If killing all processes was necessary to fix this then that means at least one task was using too
                    # much memory!
                    if n_running_processes == 0:
                        error_message = ["in order to save an out of memory issue, I had to kill *all* subprocesses. "
                                         "This means that one subprocess alone was overusing the entire memory "
                                         "budget. The following tasks were running, including their memory use:"]

                        for a_task, a_memory in zip(previous_running_tasks, previous_memory_usages):
                            error_message.append(f"{a_task}: {a_memory} GB")
                        error_message = "\n".join(error_message)

                        raise RuntimeError(error_message)

    def _kill_subprocess(self, process_index, message):
        """MURDERS a subprocess if it is MISBEHAVING. Does so immediately and resets info, other than making sure
        that it's known in the update to render to the screen that it had to be ended.
        """
        if self._greater_than_python_3_6:
            self.processes[process_index]['process'].kill()
        else:
            self.processes[process_index]['process'].terminate()

        self._close_subprocess(process_index, completed=False)
        self.processes[process_index]['update'] = message
        self._main_logfile(message)

    def _close_subprocess(self, index_to_close, completed=True):
        """Softly closes a subprocess after it ends, resetting all of the slots' info attached to the class. If
        completed=True (i.e. it is believed to have finished successfully), log data will also be written.
        """
        # Handle internal task info stuff and resource monitoring
        previous_task = self.current_task_assignments[index_to_close]
        self.current_task_assignments[index_to_close] = -1
        self.tasks_completed += 1
        self.expected_memory_usage -= self.task_information.loc[previous_task, 'expected_memory']
        self.process_cpu_usage[index_to_close] = 0
        self.process_memory_usage[index_to_close] = 0

        # Write to the tasks dataframe and save that it's done (that is, if it's actually done...)
        self.task_information.loc[previous_task, 'in_progress'] = False

        if completed:
            self.task_information.loc[previous_task, 'runtime'] = (
                    time.time() - self.task_information.loc[previous_task, 'start_time'])
            self.task_information.loc[previous_task, 'completion_time'] = datetime.datetime.now()
            self.task_information.loc[previous_task, 'remaining_to_do'] = False
            self._update_task_info_dataframe_on_disk(previous_task)

        # Reset the entry in the process list
        self.processes[index_to_close] = self.default_process_dict.copy()

    def _poll_subprocesses(self):
        """Sees how the subprocesses are doing. Formally ends any that have finished and raises a RuntimeError if
        any of them failed."""
        # Todo add more memory tracking modes, e.g. taking the mean memory usage of a process instead of the max (should
        #   work a lot better in cases where high memory use is near instantaneous)

        # Cycle over the tasks, seeing which ones are done and getting any updates
        completed_subprocesses = 0
        running_subprocesses = 0
        for i, a_process in enumerate(self.processes):
            # We only do work if the process even is running rn
            if a_process['process'] is not None:

                running_subprocesses += 1

                # See if the task has finished
                exitcode = a_process['process'].exitcode
                if exitcode is not None:
                    self._main_logfile(f"task {self.current_task_assignments[i]}: finished with exitcode {exitcode}")
                    completed_subprocesses += 1

                    # If it exited successfully, we reset the slot and record relevant info
                    if exitcode == 0:
                        self._close_subprocess(i)

                    # Otherwise, we raise an error
                    else:
                        raise ValueError(f"Process {i} failed while working on task {self.current_task_assignments[i]}")

                # If not, look for updates (we cycle over multiple updates if there are lots to get)
                else:
                    try:
                        while a_process['pipe'].poll():
                            a_process['update'] = a_process['pipe'].recv()

                    except EOFError:
                        a_process['update'] = timestamp(date=False) + "unable to receive update (EOFError on pipe)"

        # If we've done enough tasks to get a good enough benchmark, then allow the benchmarking thread lock to be
        # lifted.
        if self.tasks_completed > self.config['benchmarking_tasks']:
            self.current_max_threads = self.config['target_threads']

        return completed_subprocesses, running_subprocesses

    def _create_subprocesses(self):
        """Attempts to start subprocesses using first-fit packing."""
        # Firstly, calculate how many processes are running
        running_subprocesses = np.count_nonzero(self.current_task_assignments != -1)

        # Next, calculate how many processes we *could* run
        available_memory = self.config['max_memory'] - np.max([self.total_memory_usage, self.expected_memory_usage])
        max_subprocesses_to_start = self.current_max_threads - running_subprocesses

        # Start as many subprocesses as possible, if possible!
        subprocesses_started = 0
        while available_memory > 0 and subprocesses_started < max_subprocesses_to_start:
            # Try and find valid tasks
            valid_tasks = np.logical_and(np.logical_and(
                    np.invert(self.task_information['in_progress']),
                    self.task_information['remaining_to_do']),
                    self.task_information['expected_memory'] < available_memory
            )
            n_valid_tasks = np.count_nonzero(valid_tasks)

            # Start a task if one is available, or leave the while loop
            if n_valid_tasks == 0:
                break

            else:
                # Pick a task at random from everything we could try!
                if self._have_done_a_fit is False or self.config['random_task_order']:
                    task_index = valid_tasks[valid_tasks].sample().index[0]
                else:
                    task_index = valid_tasks.idxmax()

                self._start_subprocess(task_index)
                available_memory -= self.task_information.loc[task_index, 'expected_memory']
                subprocesses_started += 1

        return subprocesses_started

    def _start_subprocess(self, task_index):
        """Starts a new subprocess and assigns it to all the right stuff."""
        subprocess_to_start = (self.current_task_assignments == -1).nonzero()[0][0]

        self._main_logfile(f"task {task_index}: starting on process {subprocess_to_start}")

        # Update internal running info
        self.current_task_assignments[subprocess_to_start] = task_index
        self.task_information.loc[task_index, 'in_progress'] = True
        self.task_information.loc[task_index, 'start_time'] = time.time()
        self.expected_memory_usage += self.task_information.loc[task_index, 'expected_memory']

        # Make a communication pipe and a logger for the process
        pipe_end, pipe_start = multiprocessing.Pipe()
        self.processes[subprocess_to_start]['pipe'] = pipe_end

        new_logger = Logfile(
            self.config['logging_dir'] / f"{task_index} {timestamp(trailing_space=False)}.log", pipe_start
        )

        # Intialise the process!
        self.processes[subprocess_to_start]['process'] = multiprocessing.Process(
            target=self.config['function'],
            name=task_index,
            args=(new_logger, self.task_information.loc[task_index, 'args']),
            kwargs=self.config['kwargs'],
        )

        # Add a bit more info to the self.processes entry
        self.processes[subprocess_to_start]['update'] = timestamp(date=False) + f"Initialising from main..."

        # Start it!
        self.processes[subprocess_to_start]['process'].start()

        # Lastly, now that we can get its pid, we can make a psutil process for monitoring resource usage
        self.processes[subprocess_to_start]['psutil_process'] = psutil.Process(
            self.processes[subprocess_to_start]['process'].pid)

    def _fit_resource_usage(self, force_fit=False):
        """Updates fits to memory and CPU usage based on new datapoints, allowing the maximum number of subprocesses
        to be ran at any one time.

        Todo: a failed fit (e.g. due to bad knot placement) crashes the entire program.
        """
        # Firstly, let's only continue if we're outside of the benchmarking phase, also not allowing fits to only one
        # point, and also we only fit at specified intervals anyway
        due_to_fit = (
            (self.tasks_completed - self.last_task_count_when_we_fitted > self.config['fit_update_interval'])
                 or force_fit)

        if (self.tasks_completed >= 6 and self.tasks_completed >= self.config['benchmarking_tasks'] and due_to_fit):
            # Grab all of our logg'd data
            finished_tasks = np.invert(self.task_information['remaining_to_do'])

            log_x = np.log(self.task_information.loc[finished_tasks, 'metadata'].to_numpy())
            log_time = np.log(self.task_information.loc[finished_tasks, 'runtime'].to_numpy())
            log_memory = np.log(self.task_information.loc[finished_tasks, 'memory'].to_numpy())
            valid_memories = np.isfinite(log_memory)  # Occasionally we'll get zeroes here due to how it's measured!

            # Only continue if we're still better than the threshold
            if np.count_nonzero(valid_memories) >= 6:
                log_x, log_time, log_memory = (
                    log_x[valid_memories], log_time[valid_memories], log_memory[valid_memories])

                # Also, we need to sort them all
                sort_args = np.argsort(log_x)
                log_x, log_time, log_memory = (
                    log_x[sort_args], log_time[sort_args], log_memory[sort_args])

                # Create appropriate knot locations
                n_knots = int(np.minimum(np.floor((self.tasks_completed - 3)/2), self.config['fit_max_knots']))
                knots, knot_spacing = np.linspace(log_x[0], log_x[-1], num=n_knots, endpoint=False, retstep=True)
                knots += knot_spacing / 2  # Knots for LSQUnivariateSpline can't be

                # Make a couple of fits
                self._fit_time = LSQUnivariateSpline(
                    log_x, log_time, knots, k=1, ext='extrapolate', check_finite=True)
                self._fit_memory = LSQUnivariateSpline(
                    log_x, log_memory, knots, k=1, ext='extrapolate', check_finite=True)

                # Evaluate the expected resources of everything left to do, also correcting for:
                # - the fact that our sampling at short runtimes is likely to be poor
                # - if the fit predicts negative values (we force it to at least be the minimum)
                # - the fact that we're still in log land!
                meta_values = np.log(self.task_information.loc[self.task_information['remaining_to_do'], 'metadata'])
                minimum_time, minimum_memory = np.exp(np.min(log_time)), np.exp(np.min(log_memory))

                expected_times = np.maximum(np.maximum(
                    self._sampling_time, minimum_time), np.exp(self._fit_time(meta_values)))
                expected_memory = np.maximum(minimum_memory, np.exp(self._fit_memory(meta_values)))

                self.task_information.loc[self.task_information['remaining_to_do'], 'expected_runtime'] = expected_times
                self.task_information.loc[self.task_information['remaining_to_do'], 'expected_memory'] = expected_memory

                # Finally, let's also update the stats for currently running stuff
                self.last_task_count_when_we_fitted = self.tasks_completed
                self.expected_memory_usage = self.task_information.loc[
                    self.task_information['in_progress'], 'expected_memory'].sum()

                estimated_simultaneous_threads = np.minimum(
                    self.task_information.loc[self.task_information['remaining_to_do'], 'expected_memory'].mean()
                    * self.config['max_threads']**2 / self.config['max_memory'],
                    self.config['max_threads']
                )

                expected_remaining_time = (
                    self.task_information.loc[self.task_information['remaining_to_do'], 'expected_runtime'].sum()
                    / estimated_simultaneous_threads
                )

                if np.isfinite(expected_remaining_time):
                    try:
                        self.expected_finish_time = datetime.datetime.now() + datetime.timedelta(
                            0, expected_remaining_time)
                    except Exception:
                        self.expected_finish_time = SIX_SIX_SIX_THE_DEVILS_DATE
                else:
                    self.expected_finish_time = SIX_SIX_SIX_THE_DEVILS_DATE

                self._have_done_a_fit = True

                # ... and make a plot if desired!
                if self.tasks_completed - self.last_task_count_when_we_plotted > self.config['plot_update_interval']:
                    self.plot_resource_usage()

    def plot_resource_usage(self):
        """Makes a plot of the current resource usage fits for user inspection."""
        self._main_logfile(f"plotting resource usage so far")

        fig, ax = plt.subplots(nrows=2, ncols=1, dpi=100, figsize=(6, 6), sharex='all')

        # Firstly, let's plot the raw data
        is_finished = np.invert(self.task_information['remaining_to_do'])
        meta_value = self.task_information.loc[is_finished, 'metadata']
        runtime = self.task_information.loc[is_finished, 'runtime']
        memory = self.task_information.loc[is_finished, 'memory']

        ax[0].scatter(meta_value, runtime, s=2, c='k', label='Measured values')
        ax[1].scatter(meta_value, memory, s=2, c='k', label='Measured values')

        # Only add fits to the plot if we've done fits before
        if self._fit_time is not None and self._fit_memory is not None:
            minimum_runtime = np.log(np.maximum(np.min(runtime), self._sampling_time))
            minimum_memory = np.log(np.min(memory[memory > 0]))

            fit_range = np.linspace(np.min(meta_value), np.max(meta_value), num=100)
            log_fit_range = np.log(fit_range)
            runtime_fit = np.exp(np.maximum(self._fit_time(log_fit_range), minimum_runtime))
            memory_fit = np.exp(np.maximum(self._fit_memory(log_fit_range), minimum_memory))

            ax[0].plot(fit_range, runtime_fit, 'r-', label='Spline fit')
            ax[1].plot(fit_range, memory_fit, 'r-', label='Spline fit')

        # Beautification time!
        ax[0].set(title=f"{self.config['run_name']} resource use at {timestamp(trailing_space=False)}",
                  ylabel="Runtime (s)", yscale='log', xscale='log')
        ax[1].set(xlabel=self.config['metadata_name'], ylabel="Memory use (GB)", yscale='log', xscale='log')
        ax[0].legend(edgecolor='k')

        ax[0].minorticks_on()
        ax[1].minorticks_on()

        fig.subplots_adjust(hspace=0.05)

        # Output
        fig.savefig(self.config['logging_dir'] / f"resource_use.png", bbox_inches="tight")

        self.last_task_count_when_we_plotted = self.tasks_completed

    def _generate_basic_message(self):
        """The run-of-the-mill message to put on the user's screen."""

        message = [f"-- Latest thread updates at {timestamp(date=False)}--"]
        for i in range(len(self.processes)):
            message.append(f"{i: <{self.padding}}: {self.processes[i]['update']}")

        current_threads = np.count_nonzero(self.current_task_assignments != -1)
        message += [
            f"main: step {self.step}",
            "",
            "-- Current total resource use --",
            f"Threads: {current_threads} of {self.current_max_threads}   (max: {self.config['max_threads']})",
            f"CPU: {self.total_cpu_usage:.2f}%",
            f"RAM: {self.total_memory_usage:.2f} GB of {self.config['max_memory']:.2f} GB",
            f"     {self.expected_memory_usage:.2f} GB  (expected usage)",
            f"     {self.config['max_memory_hard_limit']:.2f} GB  (hard limit)",
            "",
            "-- Forecasts --",
            f"Remaining tasks: {self.tasks_total - self.tasks_completed}",
            f"Expected finish: {self.expected_finish_time.strftime('%y.%m.%d - %H:%M:%S')}",
        ]

        return message

    def _change_setting(self, keypress):
        # Memory settings!
        if self._config_to_change == "max_memory":
            try:
                self.config['max_memory'] = float(self._current_input)
                self._reset_input(f"Set max memory to {self.config['max_memory']} GB")
            except ValueError:
                self._reset_input(f"Unable to set max memory with this input!")

        # Limiting memory before death!
        elif self._config_to_change == "limit_memory":
            try:
                self.config['max_memory_hard_limit'] = float(self._current_input)
                self._reset_input(f"Set limiting memory to {self.config['max_memory_hard_limit']} GB")
            except ValueError:
                self._reset_input(f"Unable to set limiting memory with this input!")

        # Max number of fitting knots!
        elif self._config_to_change == "fit_max_knots":
            try:
                self.config['fit_max_knots'] = int(self._current_input)
                self._reset_input(f"Set max fit knots to {self.config['fit_max_knots']}")
            except ValueError:
                self._reset_input(f"Unable to set max fit knots with this input!")

        # Number of current threads!
        elif self._config_to_change == "threads":
            try:
                target_threads = int(self._current_input)
                if target_threads > self.config['max_threads']:
                    raise ValueError
                else:
                    self.config['target_threads'] = self.current_max_threads = target_threads
                    self._reset_input(f"Set number of threads to {self.config['target_threads']}")
            except ValueError:
                self._reset_input(f"Unable to set number of threads with this input!")

    def _interpret_keypress(self, keypress):
        """If a key is pressed, this is where we'll present some different options to the user!"""
        # If we're already in input mode, then keep adding to the string
        if self._config_to_change is not None:
            # Enter serves as the "save" button
            if keypress == "\n":
                self._change_setting(keypress)

            # c to cancel
            elif keypress == "c":
                self._reset_input()

            # Or, we add it on to the existing input
            else:
                self._keypress_info[1] += keypress
                self._current_input += keypress

        # Otherwise, look for a new input
        else:
            # Show help text
            if keypress == "h":
                self._keypress_info[1] = "h:help m:max n:lim t:threads p:plot c:clear k:knot f:fit"

            # Change maximum memory
            elif keypress == "m":
                self._keypress_info[1] = "New max memory: "
                self._current_input = ""
                self._config_to_change = "max_memory"

            # Change process-killing memory
            elif keypress == "n":
                self._keypress_info[1] = "New limit memory: "
                self._current_input = ""
                self._config_to_change = "limit_memory"

            # Change number of threads
            elif keypress == "t":
                self._keypress_info[1] = f"New number of threads (max {self.config['max_threads']}): "
                self._current_input = ""
                self._config_to_change = "threads"

            # Change number of fit knots
            elif keypress == "k":
                self._keypress_info[1] = f"New number of fit knots: "
                self._current_input = ""
                self._config_to_change = "fit_max_knots"

            # Perform a fit
            elif keypress == "f":
                self._keypress_info[1] = f"Performing a resource usage fit!"
                self._fit_resource_usage(force_fit=True)

            elif keypress == "p":
                self._keypress_info[1] = "Plotting current resource usage!"
                self.plot_resource_usage()

            # Clear the output lines and cancel any previous input attempt
            elif keypress == "c":
                self._reset_input()

            # Otherwise, we don't know what they want
            else:
                # Fix some keys that cause crashes
                if keypress == "\n":
                    keypress = "ENTER"

                self._keypress_info[1] = f"Key {keypress} not recognised!"

    def _reset_input(self, message=""):
        self._keypress_info = ["", message]
        self._current_input = ""
        self._config_to_change = None

    def render_console(self, stdscr):
        # Try to get a key press
        try:
            keypress = stdscr.getkey()
        except CursesError as e:
            keypress = None

        # If there has been a keypress, pass this to the interpreting function which will give some lines to show
        # self.interpret_keypress will set its info on the variable self._keypress_info, a length 2 list of strings
        if keypress is not None:
            self._interpret_keypress(keypress)

        message = self._generate_basic_message() + self._keypress_info

        # Clear screen differently depending on its size
        n_lines = len(message)
        if n_lines != self._last_window_size[0]:
            self._last_window_size = (n_lines, self._last_window_size[1])
            stdscr.clear()
            stdscr.resize(*self._last_window_size)
            curses.resizeterm(*self._last_window_size)
            # stdscr.refresh()
        else:
            stdscr.clear()

        # Add output to the terminal. We add as many lines as we can but prioritise having the last most important
        # ones be visible!
        try:
            for line_number, text in enumerate(message[-self._last_window_size[0]:]):
                stdscr.addstr(line_number, 0, text)

        except CursesError as e:
            raise e
            # pass

        # Render!
        stdscr.refresh()

    def run(self):
        self._main_logfile("Running subprocess handler.", send_to_print=True)
        curses.use_env(False)  # Allows window to be the wrong size without curses crashing

        # Try to run, if we hit an error we try to kill child processes & be informative
        try:
            curses.wrapper(self._run_with_multiline_console)

        except Exception as e:

            self._main_logfile("-- FATAL ERROR ENCOUNTERED --", send_to_print=True)
            self._main_logfile(f"{e.__class__}: {str(e)}", send_to_print=True)
            self._main_logfile("Killing all child processes!", send_to_print=True)

            for i, a_process in enumerate(self.processes):
                if a_process['process'] is not None:
                    try:
                        self._main_logfile(f"Killing process {i}, task {self.current_task_assignments[i]}",
                                           send_to_print=True)
                        self._kill_subprocess(i, "FATAL ERROR IN MAIN THREAD")

                    # We don't stop raising the main error if a process can't be killed successfully!
                    except Exception:
                        pass

            self._main_logfile("Child processes killed, terminating program. Bye =(", send_to_print=True)

            raise e

        self._main_logfile("All done! Exiting run().", send_to_print=True)

    def _run_with_multiline_console(self, stdscr):
        """I should only be used when called by the run() function which initialises multi-line console output support
        safely in a way that returns in the event of an exception.
        """
        stdscr.nodelay(True)  # Prevents key input from blocking
        self._last_window_size = stdscr.getmaxyx()

        # Main iteration of the handler
        self.step = 0
        while self.tasks_completed < self.tasks_total:

            # Check on the existing processes
            self._check_memory_usage()
            completed_subprocesses, running_subprocesses = self._poll_subprocesses()

            # If anything has changed, then refit the memory/CPU usage and make new subprocesses if possible
            if completed_subprocesses > 0:
                self._fit_resource_usage()
                subprocesses_started = self._create_subprocesses()

            elif running_subprocesses == 0 or running_subprocesses < self.current_max_threads:
                subprocesses_started = self._create_subprocesses()

            # Update the user
            self.step += 1
            self.render_console(stdscr)

            time.sleep(self.config['main_thread_sleep_time'])

        self.plot_resource_usage()
