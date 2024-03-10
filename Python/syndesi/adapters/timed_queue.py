import queue
from time import time
from typing import Tuple

class TimedQueue:
    def __init__(self) -> None:
        self._queue = queue.Queue()

    def put(self, fragment : bytes) -> None:
        self._queue.put((time(), fragment))

    def get(self, timeout : float | None) -> Tuple[float, bytes]:
        """
        Return an element of the timed queue. Waits at most the amount of time specified by timeout

        Parameters
        ----------
        timeout : float, None
        """
        try:
            return self._queue.get(block=True, timeout=timeout)
        except queue.Empty: # No item after timeout
            return None, None

    def is_empty(self):
        return self._queue.empty()
        
    def clear(self):
        with self._queue.mutex:
            self._queue.queue.clear()
            self._queue.all_tasks_done.notify_all()
            self._queue.unfinished_tasks = 0