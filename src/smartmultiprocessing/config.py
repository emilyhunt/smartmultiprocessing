from ctypes import Union
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import psutil
from smartmultiprocessing.gui.base import SmartMultiprocessingGui

from smartmultiprocessing.gui.printer import PrintGUI


def usable_physical_cpu_count():
    physical_cpu_count = psutil.cpu_count(logical=False)
    usable_cpu_fraction = psutil.cpu_count(logical=True) / len(
        psutil.Process().cpu_affinity()
    )
    usable_cpu_count = int(physical_cpu_count * usable_cpu_fraction)
    if usable_cpu_count < 1:
        raise RuntimeError("CPU count could not be automatically estimated.")
    return usable_cpu_count


def total_system_memory():
    return psutil.virtual_memory().total


PHYSICAL_CORE_COUNT = usable_physical_cpu_count()
TOTAL_PHYSICAL_MEMORY = total_system_memory()
DEFAULT_MEMORY_PER_PROCESS = int(TOTAL_PHYSICAL_MEMORY / PHYSICAL_CORE_COUNT * 0.7)


@dataclass
class Config:
    # Metadata
    name: str = "Untitled_SmartMultiprocessing_Run"
    gui: Optional[SmartMultiprocessingGui] = PrintGUI

    # How processes are handled
    process_count: int = PHYSICAL_CORE_COUNT
    memory: int = int(0.6 * TOTAL_PHYSICAL_MEMORY)
    max_memory: int = int(0.8 * TOTAL_PHYSICAL_MEMORY)
    error_on_overmemory: bool = False
    stop_all_on_error: bool = True
    failed_task_repeats: int = 0

    # Logging information
    log_main_thread: bool = False
    logging_directory: Union[str, Path] = Path("./logs")
    log_every_process: bool = False
