import pytest
from backend.routers import auth as auth_module
from backend.middleware.rate_limit import _attempts_store
from backend.routers.files import files_db
from datetime import datetime


@pytest.fixture(autouse=True)
def reset_state():
    """Reset all in-memory state between tests."""
    auth_module._users.clear()
    auth_module._revoked_refresh_token_hashes.clear()
    _attempts_store.clear()
    files_db.clear()
    files_db[1] = {"name": "file1.txt", "deleted_at": None}
    files_db[2] = {"name": "file2.txt", "deleted_at": None}
    yield
