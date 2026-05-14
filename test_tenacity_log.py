import asyncio
import logging
import structlog
from tenacity import retry, before_sleep_log

structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    processors=[structlog.processors.JSONRenderer()]
)

log = structlog.get_logger("test")

@retry(before_sleep=before_sleep_log(log, logging.WARNING))
async def fail_func():
    raise Exception("Test error")

asyncio.run(fail_func())
