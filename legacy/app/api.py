"""Opt-in old Ava API. Normal backend.app.api never enables these routes."""
from backend.app.api import create_app as staff_app, passwords

def create_app(sessions, calendar=None, llm=None, voice_enabled=True):
    return staff_app(sessions, calendar, llm, voice_enabled, legacy_enabled=True)
