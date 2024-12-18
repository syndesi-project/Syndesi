from typing import Union, Tuple, Callable
from enum import Enum
from time import time

class StopCondition:
    def __init__(self) -> None:
        """
        A condition to stop reading from a device

        Cannot be used on its own
        """
        self._and = None
        self._or = None

        self._start_time = None
        self._eval_time = None

        # Time at which the evaluation command is run

    def initiate_read(self) -> Union[float, None]:
        """
        Initiate a read sequence.

        The maximum time that should be spent in the next byte read
        is returned

        Returns
        -------
        timeout : float or None
            None is there's no timeout
        """
        return NotImplementedError()

    def evaluate(self, fragment : bytes) -> Tuple[bool, Union[float, None]]:
        """
        Evaluate the next received byte

        Returns
        -------
        stop : bool
            False if read should continue
            True if read should stop
        kept_fragment : bytes
            Part of the fragment kept for future use
        deferred_fragment : bytes
            Part of the fragment that was deferred because of a stop condition
        """
        raise NotImplementedError()


            

class Termination(StopCondition):
    def __init__(self, sequence : bytes) -> None:
        """
        Stop reading once the desired sequence is detected

        Parameters
        ----------
        sequence : bytes
        """
        super().__init__()
        if isinstance(sequence, str):
            self._termination = sequence.encode('utf-8')
        elif isinstance(sequence, bytes):
            self._termination = sequence
        else:
            raise ValueError(f"Invalid termination sequence type : {type(sequence)}")

        #self._fragment_store = b''
        #self._sequence_index = 0

    def initiate_read(self):
        super().initiate_read()
        #self._sequence_index = 0
        #self._fragment_store = b''
        return None

    def evaluate(self, fragment: bytes) -> Tuple[bool, Union[float, None]]:

        ## How to do multi-byte sequences ?
        ## What if the first part of the sequence was already confirmed and we
        ## need to "go back" and remove it
        ##
        ## Maybe the evaluate should read the whole output each time
        ## Not great but it's easier, especially for the Length stop condition
        ## Solution : Hold the last segment if the termination sequence wasn't detected

        # If there's a stored fragment (in case of an unfinished termination, append it at the beginning)
        #fragment = self._fragment_store + fragment
        #self._fragment_store = b''

        def end_contains_partial_b(a, b) -> bool:
            """
            Check if b is partially contained at the end of a

            Return the length of b contained in a
            """
            # First check b[:1] at a[-1:]
            # Then b[:2] at a[-2:]
            for i in range(1, len(b)):
                if a[-i:] == b[:i]:
                    # Match
                    return i
            return 0

        try:
            termination_index = fragment.index(self._termination)
            deferred_from = termination_index + len(self._termination)
            # Great we found it ! return the fragments
            stop = True
        except ValueError:
            stop = False
            # The entire termination wasn't found, try and see if at least the start
            # of the termination is found at the end of the fragment
            b_in_a = end_contains_partial_b(fragment, self._termination)
            # If b_in_a == 0, there's nothing ressembling a termination
            # If b_in_a > 0, part of the termination is here
            termination_index = len(fragment) - b_in_a
            deferred_from = termination_index

        return stop, fragment[:termination_index], fragment[deferred_from:]
        
    def recover_stored_fragment(self):
        """
        If, for some reason, an unfinished termination has happened (i.e. a termination
        started in a fragment and ended in another, the start of the termination in the first
        fragment is stored and is reused when the next fragment is managed.

        If a timeout occurs before the next fragment, this methods allows the user to recover
        the stored data
        """
        output = self._fragment_store
        self._fragment_store = b''
        return output

    def __repr__(self) -> str:
        return self.__str__()

    def __str__(self) -> str:
        return f'Termination({repr(self._termination)})'

# TODO : Add a "allow_longer" parameter ? If more than N data is received, keep it instead of raising an error ?
class Length(StopCondition):
    def __init__(self, N : int) -> None:
        """
        Stop condition when the desired number of bytes is reached or passed
        
        Parameters
        ----------
        N : int
            Number of bytes
        """
        super().__init__()
        self._N = N
        self._counter = 0

    def initiate_read(self):
        super().initiate_read()
        self._counter = 0

    def evaluate(self, data: bytes) -> Tuple[bool, Union[float, None]]:
        remaining_bytes = self._N - self._counter
        kept_fragment = data[:remaining_bytes]
        deferred_fragment = data[remaining_bytes:]
        self._counter += len(kept_fragment)
        remaining_bytes = self._N - self._counter
        # TODO : remaining_bytes <= 0 ? Alongside above TODO maybe
        return remaining_bytes == 0, kept_fragment, deferred_fragment

    def __repr__(self) -> str:
        return self.__str__()
        
    def __str__(self) -> str:
        return f'Length({self._N})'



# class Lambda(StopCondition):
#     class LambdaReturn:
#         ERROR = 'error' # Discard everything and raise an error
#         VALID = 'valid' # Return everything
#         KEEP_N = 'keep_n' # Keep the first N bytes
#         CONTINUE = 'continue' # Keep reading

#     def __init__(self, _lambda : Callable) -> None:
#         super().__init__()
#         self._lambda = _lambda

#     def initiate_read(self) -> Union[float, None]:
#         return None
    
#     def evaluate(self, fragment: bytes) -> Tuple[bool, Union[float, None]]:
#         lambda_return, N = self._lambda(fragment)
#         match lambda_return:
#             case self.LambdaReturn.ERROR:
#                 raise RuntimeError(f"Couldn't apply Lambda condition on fragment : {fragment}")
#             case self.LambdaReturn.VALID:
#                 return True, fragment, b''
#             case self.LambdaReturn.KEEP_N:
#                 return True, fragment[:N], fragment[N:]
#             case self.LambdaReturn.CONTINUE:
#                 return False, fragment, b'' # TODO : Check this

#     def __repr__(self) -> str:
#         return self.__str__()
    
#     def __str__(self) -> str:
#         return f'Lambda(...)'
    