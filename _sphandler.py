"""Definition of the main class of the module."""

import numpy as np
import pandas as pd
import curses
import time
import datetime
import multiprocessing

from .utilities import timestamp, Logfile


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
        print(timestamp() + "Initialising SubprocessHandler...")
        self.config = config
        self.config['logging_dir'].mkdir(exist_ok=True, parents=True)

        # Storage space for processes themselves
        self.current_task_assignments = np.full(self.config['max_threads'], -1)  # Array indicating target index of each task
        self.default_process_dict = {'update': '-', 'process': None}
        self.processes = [self.default_process_dict.copy() for i in range(self.config['max_threads'])]

        if self.config['benchmarking_tasks'] > 0:
            self.current_max_threads = 1

        # Some numbers on current tasks
        self.tasks_total = len(config['args'])
        self.tasks_completed = 0

        # Generate a more sophisticated dataframe of task info storage
        self.task_information, self.completed_tasks_log, self.write_header = self._generate_task_info_dataframe()

        # Display settings
        self.padding = len(str(self.config['max_threads']))

        # Resource tracking space
        self.current_cpu_usage = 0.0
        self.current_memory_usage = 0.0
        self.expected_memory_usage = 0.0
        self.expected_finish_time = datetime.datetime(year=6666, month=6, day=6, hour=6, minute=6, second=6)  # lol
        self.step = 0

        print(timestamp() + "Initialisation complete!")

    def _generate_task_info_dataframe(self):
        """Generates a task info dataframe in the initial startup of the program."""
        # Look for an existing df
        completed_tasks_log = self.config['logging_dir'] / f"{self.config['run_name']}_completed_tasks.csv"
        if completed_tasks_log.exists():
            existing_task_information = pd.read_csv(completed_tasks_log)
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
            'runtime': np.nan,
            'memory': np.nan,
            'expected_runtime': 1.0,
            'expected_memory': 0.1,  # Todo need expected values here
            'completion_time': 0,
            'remaining_to_do': True,
        })

        if existing_task_information is not None:
            task_information = pd.concat([existing_task_information, task_information], ignore_index=True)

        return task_information, completed_tasks_log, write_header

    def _update_task_info_dataframe_on_disk(self, indexes_to_write):
        """Appends a line or lines to the task info dataframe. Will write a header if the file didn't exist before."""
        lines_to_append = self.task_information.loc[np.atleast_1d(indexes_to_write)]
        lines_to_append.to_csv(self.completed_tasks_log, index=False, mode='a', header=self.write_header)
        self.write_header = False

    def _check_memory_usage(self):
        """Monitors the memory usage of the respective subprocesses and code. In the event of a memory limit being
        reached, this function will kill the lowest priority processes."""
        pass

    def _close_subprocess(self, index_to_close):
        """Softly closes a subprocess after it ends."""
        # Handle internal task info stuff and resource monitoring
        previous_task = self.current_task_assignments[index_to_close]
        self.current_task_assignments[index_to_close] = -1
        self.tasks_completed += 1
        self.expected_memory_usage -= self.task_information.loc[previous_task, 'expected_memory']

        # Write to the tasks dataframe and save that it's done
        self.task_information.loc[previous_task, 'runtime'] = time.time() - self.processes[index_to_close]['start_time']
        self.task_information.loc[previous_task, 'completion_time'] = datetime.datetime.now()
        self.task_information.loc[previous_task, 'remaining_to_do'] = False
        self._update_task_info_dataframe_on_disk(previous_task)

        # Reset the entry in the process list
        self.processes[index_to_close] = self.default_process_dict.copy()

    def _poll_subprocesses(self):
        """Sees how the subprocesses are doing. Formally ends any that have finished and raises a RuntimeError if
        any of them failed."""

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
                    completed_subprocesses += 1

                    # If it exited successfully, we reset the slot and record relevant info
                    if exitcode == 0:
                        self._close_subprocess(i)

                    # Otherwise, we raise an error
                    else:
                        raise ValueError(f"Process {i} failed while working on task {self.current_task_assignments[i]}")

                # If not, look for updates (we cycle over multiple updates if there are lots to get)
                else:
                    while a_process['pipe'].poll():
                        a_process['update'] = a_process['pipe'].recv()

        # If we've done enough tasks to get a good enough benchmark, then allow the benchmarking thread lock to be
        # lifted.
        if self.tasks_completed > self.config['benchmarking_tasks']:
            self.current_max_threads = self.config['max_threads']

        return completed_subprocesses, running_subprocesses

    def _create_subprocesses(self):
        """Attempts to start subprocesses using first-fit packing."""
        # Firstly, calculate how many processes are running
        running_subprocesses = np.count_nonzero(self.current_task_assignments != -1)

        # Next, calculate how many processes we *could* run
        available_memory = self.config['max_memory'] - np.max([self.current_memory_usage, self.expected_memory_usage])
        max_subprocesses_to_start = self.current_max_threads - running_subprocesses

        # Start as many subprocesses as possible, if possible!
        subprocesses_started = 0
        while available_memory > 0 and subprocesses_started < max_subprocesses_to_start:
            # Try and find valid tasks
            valid_tasks = np.logical_and(
                    self.task_information['remaining_to_do'],
                    self.task_information['expected_memory'] < available_memory
            )
            n_valid_tasks = np.count_nonzero(valid_tasks)

            # Start a task if one is available, or leave the while loop
            if n_valid_tasks == 0:
                break
            else:
                task_index = valid_tasks.idxmax()
                self._start_subprocess(task_index)
                available_memory -= self.task_information.loc[task_index, 'expected_memory']
                subprocesses_started += 1

        return subprocesses_started

    def _start_subprocess(self, task_index):
        """Starts a new subprocess and assigns it to all the right stuff."""
        subprocess_to_start = (self.current_task_assignments == -1).nonzero()[0][0]

        # Update internal running info
        self.current_task_assignments[subprocess_to_start] = task_index
        self.task_information.loc[task_index, 'remaining_to_do'] = False
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
            args=(new_logger, task_index),
        )

        # Add a bit more info to the self.processes entry
        self.processes[subprocess_to_start]['update'] = timestamp(date=False) + f"Initialising from main..."
        self.processes[subprocess_to_start]['start_time'] = time.time()

        # Lastly, start it!
        self.processes[subprocess_to_start]['process'].start()

    def _fit_resource_usage(self):
        """Updates fits to memory and CPU usage based on new datapoints, allowing the maximum number of subprocesses
        to be ran at any one time."""
        # Todo

        pass

    def plot_resource_usage(self):
        """Makes a plot of the current resource usage fits for user inspection."""
        # Todo

        pass

    def render_console(self, stdscr):
        # Clear screen
        stdscr.clear()

        # Add output to the terminal
        stdscr.addstr(0, 0, f"-- Latest thread updates at {timestamp(date=False)}--")

        i = 0  # We need to declare this in case there are no threads (why would that happen, I dunno)
        for i in range(len(self.processes)):
            stdscr.addstr(i+1, 0, f"{i: <{self.padding}}: {self.processes[i]['update']}")

        stdscr.addstr(i + 2, 0, f"main: step {self.step}")

        stdscr.addstr(i + 4, 0, "-- Current total resource use --")
        current_threads = np.count_nonzero(self.current_task_assignments != -1)
        stdscr.addstr(i + 5, 0, f"Threads: {current_threads} of {self.current_max_threads}")
        stdscr.addstr(i + 6, 0, f"CPU: {self.current_cpu_usage:.3f}")
        stdscr.addstr(i + 7, 0, f"RAM: {self.current_memory_usage:.3f} GB of {self.config['max_memory']:.3f} GB")
        stdscr.addstr(i + 8, 0, f"     {self.expected_memory_usage:.3f} GB  (expected usage)")

        stdscr.addstr(i + 10, 0, "-- Forecasts --")
        stdscr.addstr(i + 11, 0, f"Remaining tasks: {self.tasks_total - self.tasks_completed}")
        stdscr.addstr(i + 12, 0, f"Expected finish: {self.expected_finish_time.strftime('%y.%m.%d - %H:%M:%S')}")

        # Render & get keyboard
        stdscr.refresh()
        # stdscr.getkey()

    def run(self):
        print(timestamp() + "Running subprocess handler.")
        curses.use_env(False)  # Allows window to be the wrong size without curses crashing
        curses.wrapper(self._run_with_multiline_console)
        print(timestamp() + "All done! Exiting run().")

    def _run_with_multiline_console(self, stdscr):
        """I should only be used when called by the run() function which initialises multi-line console output support
        safely in a way that returns in the event of an exception.
        """
        stdscr.nodelay(True)  # Prevents key input from blocking

        # Main iteration of the handler
        self.step = 0
        while self.tasks_completed < self.tasks_total:

            # Check on the existing processes
            self._check_memory_usage()
            completed_subprocesses, running_subprocesses = self._poll_subprocesses()

            # If anything has changed, then refit the memory/CPU usage and make new subprocesses if possible
            if completed_subprocesses > 0 or running_subprocesses == 0:
                self._fit_resource_usage()
                subprocesses_started = self._create_subprocesses()

            # Update the user
            self.step += 1
            self.render_console(stdscr)

            time.sleep(self.config['main_thread_sleep_time'])
