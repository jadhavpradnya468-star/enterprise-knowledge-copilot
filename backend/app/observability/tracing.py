"""Request-ID logging and a decorator that records per-node trace entries."""
import contextvars
import functools
import logging
import time

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
logger = logging.getLogger("app.workflow")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def traced(name: str):
    """Wrap a graph node: time it, capture errors, and append a trace entry.

    The node may return a "_detail" dict (chunk ids, token counts, ...) which is copied into the
    trace entry. Raw document text and prompts are never written to the trace or logs.
    """

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state):
            start = time.perf_counter()
            status, detail = "ok", {}
            try:
                update = dict(fn(state) or {})
                detail = update.pop("_detail", {})
            except Exception as exc:  # noqa: BLE001
                logger.error("node=%s failed: %s", name, type(exc).__name__)
                update = {"error": f"{name} failed ({type(exc).__name__})"}
                status, detail = "error", {"error_type": type(exc).__name__}
            latency = round((time.perf_counter() - start) * 1000, 1)
            update["trace"] = [{"node": name, "status": status, "latency_ms": latency, **detail}]
            logger.info("node=%s status=%s latency_ms=%s", name, status, latency)
            return update

        return wrapper

    return decorator
