# File : timed_queue.py
# Author : Sébastien Deriaz
# License : GPL
#
# The timed queue is a special queue that stores time information when elements are stored inside
# This is used to manage timing when reading data from devices

# import queue
# from time import time


# class TimedQueue:
#     def __init__(self) -> None:
#         self._queue = queue.Queue()

#     def put(self, fragment: bytes) -> None:
#         self._queue.put((time(), fragment))

#     def get(self, timeout: float | None) -> tuple[float, bytes]:
#         """
#         Return an element of the timed queue. Waits at most the amount of time specified by timeout

#         Parameters
#         ----------
#         timeout : float, None
#         """
#         try:
#             return self._queue.get(block=True, timeout=timeout)
#         except queue.Empty:  # No item after timeout
#             return None, None

#     def is_empty(self):
#         return self._queue.empty()

#     def clear(self):
#         with self._queue.mutex:
#             self._queue.queue.clear()
#             self._queue.all_tasks_done.notify_all()
#             self._queue.unfinished_tasks = 0
