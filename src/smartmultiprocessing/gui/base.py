from abc import ABCMeta, abstractmethod
from typing import Iterable, Optional
from smartmultiprocessing.gui.commands import SmartMultiprocessingCommand
from smartmultiprocessing.gui.updates import SmartMultiprocessingGuiUpdate

class SmartMultiprocessingGui(metaclass=ABCMeta):
    @abstractmethod
    def start(self):
        """Starts the GUI."""
        pass

    @abstractmethod
    def stop(self):
        """Stops the GUI."""
        pass

    @abstractmethod
    def update(self, updates: Iterable[SmartMultiprocessingGuiUpdate]):
        """Updates the current state of the GUI."""
        pass

    @abstractmethod
    def get_commands(self) -> Optional[Iterable[SmartMultiprocessingCommand]]:
        """Checks to see if there is any current user input. If yes, returns an iterable
        list of commands; if no, returns None."""
        pass
