"""A collection of little utilities that are useful for all objects."""

import datetime

from pathlib import Path
from multiprocessing.connection import Connection

from typing import Optional


def timestamp(date: bool = True, trailing_space: bool = True):
    if trailing_space:
        trail = " "
    else:
        trail = ""

    if date:
        return datetime.datetime.now().strftime("[%y.%m.%d - %H:%M:%S]") + trail
    else:
        return datetime.datetime.now().strftime("[%H:%M:%S]") + trail


class Logfile:

    def __init__(self, logfile: Path, pipe: Optional[Connection]=None):

        logfile.parent.mkdir(parents=True, exist_ok=True)

        self.logfile = logfile
        self.pipe = pipe
        self.pipe_on = True
        self.logfile_on = True

    def __call__(self, message: str, send_to_pipe: bool = True,
                 send_to_logfile: bool = True, send_to_print: bool = False):

        if send_to_pipe and self.pipe is not None and self.pipe_on:
            self.pipe.send(timestamp(date=False) + message)

        if send_to_logfile and self.logfile_on:
            with open(self.logfile, 'a') as file:
                file.write(timestamp() + message + "\n")

        if send_to_print:
            print(timestamp() + message)

    def set_pipe_on(self, state: bool):
        self.pipe_on = state

    def set_logfile_on(self, state: bool):
        self.logfile_on = state
