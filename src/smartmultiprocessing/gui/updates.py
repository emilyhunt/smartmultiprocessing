from abc import ABC, abstractmethod


class SmartMultiprocessingGuiUpdate(ABC):
    @abstractmethod
    def to_string(self):
        """Converts a GUI update to a string."""
        pass
