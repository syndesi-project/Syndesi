# This code comes from https://github.com/CasuallyCalm/dearpygui-async/blob/main/src/dearpygui_async/dearpygui_async.py
# Copying it allows the user to install dearpygui only
# Tweaks were made to make mypy and pylint happy

import asyncio
import time
from typing import Any

import dearpygui.dearpygui as dpg # type: ignore[import-untyped]


CallbackJob = tuple[Any, ...]

async def _sleep(seconds:float) -> None:
    '''An asyncio sleep.

    On Windows this achieves a better granularity than asyncio.sleep

    Args:
        seconds (float): Seconds to sleep for.
    
    '''
    await asyncio.get_running_loop().run_in_executor(None, time.sleep, seconds)

class DearPyGuiAsync:
    """DearPyGuiAsync"""

    def __init__(self, loop : asyncio.AbstractEventLoop | None = None) -> None:
        self.loop = loop or asyncio.get_event_loop()
        self._callback_task: asyncio.Task[None] | None = None

    async def setup(self) -> None:
        '''
        Special method that runs when starting
        This is helpful for running code that has special setup behavior that may be asynchronous
        '''

    async def teardown(self) -> None:
        '''
        Special method that runs when shutting down.
        This is helpful for running code that has special shutdown behavior that may be asynchronous
        '''

    async def run_callbacks(self, jobs: list[CallbackJob] | None) -> None:
        '''
        Run the callbacks that were added
        '''
        if jobs is None:
            pass
        else:
            for job in jobs:
                if job[0] is None:
                    pass
                else:
                    sig = dpg.inspect.signature(job[0])
                    args = []
                    for arg in range(len(sig.parameters)):
                        args.append(job[arg + 1])
                    if asyncio.iscoroutinefunction(
                        job[0]
                    ) or asyncio.iscoroutinefunction(job[0].__call__):
                        try:
                            await job[0](*args)
                        except Exception as e: # pylint: disable=
                            print(e)
                    else:
                        job[0](*args)


    async def callback_loop(self) -> None:
        '''
        |coro|
        Processes the the callbacks asynchronously
        This will configure the app to manually manage the callbacks so overwrite this if you want to do something else
        '''
        dpg.configure_app(manual_callback_management=True)
        while dpg.is_dearpygui_running():
            asyncio.create_task(self.run_callbacks(dpg.get_callback_queue()))
            dpg.render_dearpygui_frame()
            await _sleep(0.0095)
        await self.teardown() 

    async def start(self) -> None:
        '''
        |coro|
        For starting the gui in an async context
        Usually to add a gui to another async process
        '''
        await self.setup()
        self._callback_task = asyncio.create_task(self.callback_loop()) 
    
    async def __start(self) -> None:
        await self.setup()
        await self.callback_loop()

    async def stop(self) -> None:
        '''
        |coro|
        Manually cancel the callback processing task
        '''
        if self._callback_task is not None:
            self._callback_task.cancel()
        await self.teardown()

    def run(self) -> None:
        '''
        |blocking|
        Run DearPyGui with async compatibility
        Use this in place of `dpg.start_gui()`
        
        '''
        self.loop.run_until_complete(self.__start())
