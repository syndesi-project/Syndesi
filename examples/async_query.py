"""The same, with async / await. Start echo_server.py first"""

import asyncio

from syndesi import AsyncDelimited, AsyncIP


async def main():
    async with AsyncDelimited(AsyncIP("127.0.0.1", 4242)) as device:
        print(await device.query("Hello"))  # 'Hello'


asyncio.run(main())
