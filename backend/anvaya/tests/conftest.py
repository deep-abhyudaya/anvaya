"""Pytest configuration.

Importing the FastAPI entry module first breaks the anvaya.agent <->
anvaya.generations.builder circular import that exists during isolated module
imports, because main.py brings in all routers in the order the application
expects at runtime.
"""

import anvaya.main  # noqa: F401
