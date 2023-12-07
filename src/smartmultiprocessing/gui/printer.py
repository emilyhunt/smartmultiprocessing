from typing import Iterable
from smartmultiprocessing import utilities
from smartmultiprocessing.gui.base import SmartMultiprocessingGui
from smartmultiprocessing.gui.updates import SmartMultiprocessingGuiUpdate


class PrintGUI(SmartMultiprocessingGui):
    def __init__(self) -> None:
        """The most basic possible SmartMultiprocessing GUI! It simply prints to
        console.
        
        You should probably check out the more advanced GUIs implemented in the library;
        this one is only really intended for testing purposes, or systems with very
        limited resources.
        """
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def update(self, updates: Iterable[SmartMultiprocessingGuiUpdate]):
        for update in updates:
            print(utilities.timestamp() + update.to_string())

    def get_commands(self):
        return None
