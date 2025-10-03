# File : timeout.py
# Author : Sébastien Deriaz
# License : GPL
#
# The timeout backend manages timing when reading from a device, it both
# records how much time each action took and stops communication if it
# exceeds set criteria

# from enum import Enum
# from typing import Union, Tuple
# from time import time
# import json

# class TimeoutAction(Enum):
#     DISCARD = "discard"  # If a timeout is reached, data is discarded
#     RETURN = "return"  #  If a timeout is reached, data is returned (timeout acts as a stop condition)
#     STORE = "store"  # If a timeout is reached, data is stored and returned on the next read() call
#     ERROR = "error"  # If a timeout is reached, raise an error


# class TimeoutType(Enum):
#     RESPONSE = "response"

# class JsonKey(Enum):
#     RESPONSE = "r"
#     ACTION = "a"


# class TimeoutBackend:
#     class _State(Enum):
#         WAIT_FOR_RESPONSE = 0
#         CONTINUATION = 1

#     def __init__(
#         self, response, continuation, total, on_response, on_continuation, on_total
#     ) -> None:
#         """
#         A class to manage timeouts

#         Timeouts are split in three categories :
#         - response timeout : the "standard" timeout, (i.e the time it takes for
#             a device to start transmitting data)
#         - continuation timeout : the time between reception of
#             data units (bytes or blocks of data)
#         - total timeout : maximum time from start to end of transmission.
#             This timeout can stop a communication mid-way. It is used to
#             prevent a host from getting stuck reading a constantly streaming device

#         Each timeout is specified in seconds

#         Actions
#         - discard : Discard all of data obtained during the read() call if the specified timeout if reached and return empty data
#         - return : Return all of the data read up to this point when the specified timeout is reached
#         - store : Store all of the data read up to this point in a buffer. Data will be available at the next read() call
#         - error : Produce an error

#         Parameters
#         ----------
#         response : float
#         continuation : float
#         total : float
#         on_response : str
#             Action on response timeout (see Actions)
#         on_continuation : str
#             Action on continuation timeout (see Actions)
#         on_total : str
#             Action on total timeout (see Actions)
#         """
#         super().__init__()
#         # It is possible to pass a tuple to set response/continuation/total, parse this first if it is the case
#         if isinstance(response, (tuple, list)):
#             if len(response) >= 3:
#                 total = response[2]
#             if len(response) >= 2:
#                 continuation = response[1]
#             response = response[0]

#         # Timeout values (response, continuation and total)
#         self._response = response
#         self._continuation = continuation
#         self._total = total
#         self._on_response = (
#             TimeoutAction(on_response) if on_response is not None else None
#         )
#         self._on_continuation = (
#             TimeoutAction(on_continuation) if on_continuation is not None else None
#         )
#         self._on_total = TimeoutAction(on_total) if on_total is not None else None

#         # State machine flags
#         self._state = self._State.WAIT_FOR_RESPONSE
#         self._queue_timeout_type = TimeoutType.RESPONSE
#         self._last_data_action_origin = TimeoutType.RESPONSE

#     def initiate_read(self, deferred_buffer: bool = False) -> Union[float, None]:
#         """
#         Initiate a read sequence.

#         The maximum time that should be spent in the next byte read
#         is returned

#         Returns
#         -------
#         stop : bool
#             Timeout is reached
#         keep : bool
#             True if data read up to this point should be kept
#             False if data should be discarded
#         timeout : float or None
#             None is there's no timeout
#         """
#         self._start_time = time()
#         if deferred_buffer:
#             self._state = self._State.CONTINUATION
#             self._data_action = self._on_continuation
#             self._queue_timeout_type = TimeoutType.CONTINUATION
#         else:
#             self._state = self._State.WAIT_FOR_RESPONSE
#             self._data_action = self._on_response
#             self._queue_timeout_type = TimeoutType.RESPONSE
#         self._last_timestamp = None

#         self.response_time = None
#         self.continuation_times = []
#         self.total_time = None

#         self._output_timeout = None

#         return self._response

#     def evaluate(self, timestamp: float) -> Tuple[bool, Union[float, None]]:
#         stop = False

#         # self._check_uninitialization()

#         self._data_action = None
#         self._stop_source_value = (
#             "###"  # When a timeout occurs, store the value that exceeded its value here
#         )
#         self._stop_source_limit = "###"  # And store the limit value here

#         # First check if the timestamp is None, that would mean the timeout was reached in the queue
#         if timestamp is None:
#             # Set the data action according to the timeout that was given for the queue before
#             match self._queue_timeout_type:
#                 case TimeoutType.RESPONSE:
#                     self._data_action = self._on_response
#                     self._stop_source_limit = self._response
#                 case TimeoutType.CONTINUATION:
#                     self._data_action = self._on_continuation
#                     self._stop_source_limit = self._continuation
#                 case TimeoutType.TOTAL:
#                     self._data_action = self._on_total
#                     self._stop_source_limit = self._total
#             self._stop_source_value = None  # We do not have the exceed time, but None will be printed as '---'
#             self._last_data_action_origin = self._queue_timeout_type
#             stop = True

#         else:
#             # Check total
#             if self._total is not None:
#                 self.total_time = timestamp - self._start_time
#                 if self.total_time >= self._total:
#                     stop = True
#                     self._data_action = self._on_total
#                     self._last_data_action_origin = TimeoutType.TOTAL
#                     self._stop_source_value = self.total_time
#                     self._stop_source_limit = self._total
#             # Check continuation
#             elif (
#                 self._continuation is not None
#                 and self._state == self._State.CONTINUATION
#                 and self._last_timestamp is not None
#             ):
#                 continuation_time = timestamp - self._last_timestamp
#                 self.continuation_times.append(continuation_time)
#                 if continuation_time >= self._continuation:
#                     stop = True
#                     self._data_action = self._on_continuation
#                     self._last_data_action_origin = TimeoutType.CONTINUATION
#                     self._stop_source_value = continuation_time
#                     self._stop_source_limit = self._continuation
#             # Check response time
#             elif (
#                 self._response is not None
#                 and self._state == self._State.WAIT_FOR_RESPONSE
#             ):
#                 self.response_time = timestamp - self._start_time
#                 if self.response_time >= self._response:
#                     stop = True
#                     self._data_action = self._on_response
#                     self._last_data_action_origin = TimeoutType.RESPONSE
#                     self._stop_source_value = self.response_time
#                     self._stop_source_limit = self._response

#         self._output_timeout = None
#         # If we continue
#         if not stop:
#             # Update the state
#             if self._state == self._State.WAIT_FOR_RESPONSE:
#                 self._state = self._State.CONTINUATION
#             self._last_timestamp = timestamp
#             # No timeouts were reached, return the next one
#             # Return the timeout (state is always CONTINUATION at this stage)
#             # Take the smallest between continuation and total
#             if self._total is not None and self._continuation is not None:
#                 c = self._continuation
#                 t = self._start_time + self._total
#                 if c < t:
#                     self._output_timeout = c
#                     self._queue_timeout_type = TimeoutType.CONTINUATION
#                 else:
#                     self._output_timeout = t
#                     self._queue_timeout_type = TimeoutType.TOTAL
#             elif self._total is not None:
#                 self._output_timeout = time() - (self._start_time + self._total)
#                 self._queue_timeout_type = TimeoutType.TOTAL
#             elif self._continuation is not None:
#                 self._output_timeout = self._continuation
#                 self._queue_timeout_type = TimeoutType.CONTINUATION

#         return stop, self._output_timeout

#     def dataAction(self):
#         """
#         Return the data action (discard, return, store or error)
#         and the timeout origin (response, continuation or total)

#         Returns
#         -------
#         data_action : Timeout.DataAction
#         origin : Timeout.TimeoutType

#         """
#         return self._data_action, self._last_data_action_origin

#     def __str__(self) -> str:
#         def _format(value, action):
#             if value is None:
#                 return "None"
#             elif value is Ellipsis:
#                 return "not set"
#             else:
#                 return f'{value*1e3:.3f}ms/{action.value if isinstance(action, Enum) else "not set"}'

#         response = "r:" + _format(self._response, self._on_response)
#         continuation = "c:" + _format(self._continuation, self._on_continuation)
#         total = "t:" + _format(self._total, self._on_total)
#         return f"Timeout({response},{continuation},{total})"

#     def __repr__(self) -> str:
#         return self.__str__()
