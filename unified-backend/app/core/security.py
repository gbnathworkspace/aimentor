"""Authentication and authorization — compatibility re-export.

The canonical implementation now lives in app.auth.dependencies.
This module re-exports require_auth for backward compatibility with existing
imports throughout the codebase.
"""

from app.auth.dependencies import require_auth  # noqa: F401
