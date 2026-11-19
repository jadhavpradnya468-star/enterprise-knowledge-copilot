import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="ekc_test_")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "UPLOAD_DIR": f"{_tmp}/uploads",
    "EVAL_REPORT_DIR": f"{_tmp}/reports",
    "API_KEYS": "alice:alice-key,bob:bob-key",
    "LLM_PROVIDER": "fake",
    "EMBEDDING_PROVIDER": "fake",
    "VECTOR_STORE": "local",
    "MAX_UPLOAD_MB": "1",
    "APP_ENV": "test",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ALICE = {"X-API-Key": "alice-key"}
BOB = {"X-API-Key": "bob-key"}

TRAVEL = (
    "Business travel reimbursement policy: Employees may claim reimbursement for business travel expenses "
    "including airfare and lodging. Meals are reimbursed up to 50 dollars per day."
)


@pytest.fixture()
def client():
    from app.db import Base, get_engine
    from app.main import create_app

    Base.metadata.drop_all(get_engine())
    with TestClient(create_app()) as c:
        yield c


def upload(client, headers, name="travel-policy.txt", content: bytes = TRAVEL.encode()):
    return client.post("/api/v1/documents", headers=headers, files={"file": (name, content)})
