## Async, Future and Proxy

local = LocalAdapter(...)
remote = ProxyAdapter(...)

async_local = AsyncAdapter(local)
async_remote = AsyncAdapter(remote)


```
    2) How to expose simple API + breathing room (Futures / asyncio)?

    You basically want three “layers” on top of your adapter thread:

    Very simple synchronous API (default, for most users)

    Optional Future-based API (for advanced users who still live in threaded world)

    Optional asyncio wrapper (for async people)

    Your adapter thread + command queue is the core. On top of it you can build different skins.
```


## 2025-12-18

How to make the asyncio wrapper :

It's not possible to do it with the current design, it would mean rewriting the entire read_detailed loop and using a different queue (asyncio.Queue).
There's a better solution instead : Move all of the logic to the worker thread

This way the "frontend" sends commands to the worker for everything. The sync is simply doing future.result(timeout=...) while the
async layer wraps the future in the asyncio stuff