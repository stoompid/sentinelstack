"""
Retry utility with exponential backoff.

Implements 3x retry with exponential backoff as specified.
"""

import time
import functools
from typing import Callable, TypeVar, Any
import structlog

logger = structlog.get_logger(__name__)

T = TypeVar('T')


class RetryExhausted(Exception):
    """Raised when all retry attempts have been exhausted."""
    pass


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,)
) -> Callable:
    """
    Decorator that retries a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts (default 3)
        base_delay: Initial delay in seconds (default 1.0)
        max_delay: Maximum delay between retries (default 30.0)
        exponential_base: Multiplier for each retry (default 2.0)
        exceptions: Tuple of exceptions to catch and retry
    
    Returns:
        Decorated function with retry logic
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_retries:
                        logger.error(
                            "retry_exhausted",
                            function=func.__name__,
                            attempts=max_retries + 1,
                            error=str(e)
                        )
                        raise RetryExhausted(
                            f"Failed after {max_retries + 1} attempts: {e}"
                        ) from e
                    
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )
                    
                    logger.warning(
                        "retry_attempt",
                        function=func.__name__,
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        delay=delay,
                        error=str(e)
                    )
                    
                    time.sleep(delay)
            
            # Should not reach here, but just in case
            raise last_exception
        
        return wrapper
    return decorator


async def async_retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,),
    *args: Any,
    **kwargs: Any
) -> T:
    """
    Async version of retry with exponential backoff.
    
    Use this for async functions where the decorator pattern is awkward.
    """
    import asyncio
    
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                logger.error(
                    "async_retry_exhausted",
                    function=func.__name__,
                    attempts=max_retries + 1,
                    error=str(e)
                )
                raise RetryExhausted(
                    f"Failed after {max_retries + 1} attempts: {e}"
                ) from e
            
            delay = min(
                base_delay * (exponential_base ** attempt),
                max_delay
            )
            
            logger.warning(
                "async_retry_attempt",
                function=func.__name__,
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                error=str(e)
            )
            
            await asyncio.sleep(delay)
    
    raise last_exception
