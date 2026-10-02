"""Turn-local observation of actual synchronous appointment/calendar reads."""
from contextvars import ContextVar
from contextlib import contextmanager

lookup_observer = ContextVar('lookup_observer', default=None)

@contextmanager
def appointment_lookup():
    observer = lookup_observer.get()
    if observer: observer(True)
    try:
        yield
    finally:
        if observer: observer(False)

def calendar_read(method, *args, **kwargs):
    with appointment_lookup():
        return method(*args, **kwargs)
