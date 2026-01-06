DEFAULT_REMOTE_PORT = 59677


# Backend protocol format
# (action, arguments)
# If the command succeeds, it is returned as :
# (action, other arguments)
# If the command fails, it is returned as :
# (error, error_description)


# The backend links the client with an adapter when SELECT_ADAPTER is
# sent along with an adapter descriptor

EXTRA_BUFFER_RESPONSE_TIME = 1

# Delay to let the adapter connect
DEFAULT_ADAPTER_OPEN_TIMEOUT = 0.5


# def add_backend_address_port_arguments(
#     parser: argparse.ArgumentParser, client_side: bool
# ) -> None:
#     """
#     Add -a/--address and -p/--port to a given ArgumentParser. The description of -a/--address
#     is different based on the value of client_side
#     """
#     if client_side:
#         address_help = "Address of the backend"
#     else:
#         address_help = (
#             "Backend listening address, set it to the host address used by clients"
#         )

#     parser.add_argument(
#         "-a", "--address", type=str, default=LOCALHOST, help=address_help
#     )
#     parser.add_argument("-p", "--port", type=int, default=BACKEND_PORT)


# class Action(Enum):
#     """
#     Backend actions enum
#     """

#     # All adapters
#     SELECT_ADAPTER = "select"
#     OPEN = "open"  # (descriptor,stop_condition) -> ()
#     CLOSE = "close"  # (descriptor,force) -> ()
#     # FORCE_CLOSE = "force_close"  # (descriptor,) -> ()
#     WRITE = "write"  # (descriptor,data) -> ()
#     READ = "read"  # (descriptor,full_output,temp_timeout,temp_stop_condition) -> (data,metrics)
#     SET_STOP_CONDITIONS = "set_stop_condition"  # (descriptor,stop_condition)
#     FLUSHREAD = "flushread"
#     START_READ = "start_read"  # Start a read (descriptor,response_time)
#     RESPONSE_TIMEOUT = "response_timeout"

#     # Signal
#     ADAPTER_SIGNAL = "adapter_signal"

#     # Other
#     SET_ROLE_ADAPTER = (
#         "set_role_adapter"  # Define the client as an adapter (exchange of data)
#     )
#     SET_ROLE_MONITORING = "set_role_monitoring"  # The client queries for backend info
#     SET_ROLE_LOGGER = "set_role_logger"  # The client receives logs
#     SET_LOG_LEVEL = "set_log_level"
#     PING = "ping"
#     STOP = "stop"

#     # Backend debugger
#     ENUMERATE_ADAPTER_CONNECTIONS = "enumerate_adapter_connections"
#     ENUMERATE_MONITORING_CONNECTIONS = "enumerate_monitoring_connections"
#     BACKEND_STATS = "backend_stats"

#     # Errors
#     ERROR_GENERIC = "error_generic"
#     ERROR_UNKNOWN_ACTION = "error_unknown_action"
#     ERROR_INVALID_REQUEST = "error_invalid_request"
#     ERROR_ADAPTER_NOT_OPENED = "error_adapter_not_opened"
#     ERROR_INVALID_ROLE = "error_invalid_role"
#     ERROR_ADAPTER_DISCONNECTED = "error_adapter_disconnected"
#     ERROR_BACKEND_DISCONNECTED = "error_backend_disconnected"
#     ERROR_FAILED_TO_OPEN = "error_failed_to_open"


# def is_action_error(action: Action) -> bool:
#     """
#     Return True if the action describes an error
#     """
#     return action.value.startswith("error_")


# class BackendException(Exception):
#     """
#     Generic backend error
#     """


# def frontend_send(conn: Connection, action: Action, *args: Any) -> bool:
#     """
#     Send an action to the frontend
#     """
#     try:
#         conn.send((action.value, *args))
#     except (BrokenPipeError, OSError):
#         return False
#     return True


# def backend_request(
#     conn: Connection,
#     action: Action,
#     *args: Any,
#     timeout: float = EXTRA_BUFFER_RESPONSE_TIME,
# ) -> BackendResponse:
#     """
#     Send a request to the backend an expect a response with the time specified by timeout
#     """
#     try:
#         conn.send((action.value, *args))
#     except (BrokenPipeError, OSError) as err:
#         raise BackendCommunicationError("Failed to communicate with backend") from err

#     ready = wait([conn], timeout=timeout)
#     if conn not in ready:
#         raise BackendCommunicationError("Failed to receive backend response in time")

#     try:
#         raw_response: object = conn.recv()
#     except (EOFError, ConnectionResetError) as err:
#         raise BackendCommunicationError(
#             f"Failed to receive backend response to {action.value}"
#         ) from err

#     # Check if the response is correctly formatted
#     if not (isinstance(raw_response, tuple) and isinstance(raw_response[0], str)):
#         raise BackendCommunicationError(
#             f"Invalid response received from backend : {raw_response}"
#         )

#     response_action: Action = Action(raw_response[0])
#     arguments: tuple[Any, ...] = raw_response[1:]

#     if is_action_error(response_action):
#         if len(arguments) > 0:
#             if isinstance(arguments[0], str):
#                 error_message: str = arguments[0]
#             else:
#                 error_message = "failed to read error message"
#         else:
#             error_message = "Missing error message"
#         raise BackendError(f"{response_action} : {error_message}")
#     return arguments


# backend_send = frontend_send


# def raise_if_error(response: BackendResponse) -> None:
#     """
#     Raise error if the action is an error, ignore otherwise
#     """
#     action = Action(response[0])
#     if is_action_error(action):
#         if len(response) > 1:
#             description = response[1]
#         else:
#             description = f"{action}"
#         raise BackendException(f"{action.name}/{description}")


# class AdapterBackendStatus(Enum):
#     """
#     Adapter backend status enum
#     """

#     DISCONNECTED = 0
#     CONNECTED = 1


# class ClientStatus(Enum):
#     """
#     Client status enum
#     """

#     DISCONNECTED = 0
#     CONNECTED = 1
