from abc import ABC
from typing import Any, Mapping


class SmartMultiprocessingCommand(ABC):
    pass


class StopCommand(SmartMultiprocessingCommand):
    def __init__(self) -> None:
        """Asks a system to stop after execution of all current processes."""
        raise NotImplementedError("Command not implemented.")


class TerminateCommand(SmartMultiprocessingCommand):
    def __init__(self) -> None:
        """Politely terminates a system (SIGTERM)."""
        raise NotImplementedError("Command not implemented.")


class KillCommand(SmartMultiprocessingCommand):
    def __init__(self) -> None:
        """Ask a system to stop immediately (SIGKILL)."""
        raise NotImplementedError("Command not implemented.")


class UpdateCommand(SmartMultiprocessingCommand):
    def __init__(self) -> None:
        """Updates some arbitrary aspect of the configuration of the system."""
        raise NotImplementedError("Command not implemented.")
    
    def get_update(self) -> Mapping[str, Any]:
        """Get the update to be applied to the system."""
        pass
