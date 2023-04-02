from ...wrappers.wrapper import Wrapper


class Device:
    def __init__(self, wrapper : Wrapper):
        self._wrapper = wrapper