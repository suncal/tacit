import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["TACIT_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["TACIT_BRAIN_PROVIDER"] = "local"
os.environ["TACIT_WORKSPACE"] = _tmp
os.environ["TACIT_SECRET_KEY"] = "test-secret"
os.environ["TACIT_GITHUB_TOKEN"] = ""
os.environ["TACIT_GITHUB_REPOS"] = ""
os.environ.pop("GITHUB_TOKEN", None)
os.environ.pop("GH_TOKEN", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from tacit.db import Base, engine  # noqa: E402
from tacit import models  # noqa: E402,F401
from tacit.app import TacitApp  # noqa: E402
from tacit.main import create_app  # noqa: E402
from tacit.settings import get_settings  # noqa: E402


@pytest.fixture(scope="session")
def tacit():
    Base.metadata.create_all(engine)
    return TacitApp(get_settings())


@pytest.fixture(scope="session")
def client(tacit):
    app = create_app(tacit, background=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _clean():
    """Each test starts from empty tables (schema kept)."""
    from sqlalchemy import text
    with engine.begin() as conn:
        for t in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"DELETE FROM {t.name}"))
    yield
