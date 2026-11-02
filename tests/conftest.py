from pathlib import Path
from typing import Generator
import uuid
import pytest
from sqlalchemy import Engine

from backend.database import get_db
from shared.db import drop_session_replica


@pytest.fixture(scope="session")
def db_engine() -> Engine:
    """Provides a singleton SQLAlchemy database engine connected to the application database."""
    return get_db()


@pytest.fixture
def test_session_id(db_engine: Engine) -> Generator[str, None, None]:
    """Generates an isolated session identifier and guarantees schema cleanup after test execution."""
    session_id = f"test_{uuid.uuid4().hex[:12]}"
    try:
        yield session_id
    finally:
        try:
            drop_session_replica(db_engine, session_id)
        except Exception:
            pass


@pytest.fixture
def valid_csv_content() -> str:
    """Returns valid tabular CSV content with diverse column types."""
    return (
        "id,product_name,category,price,stock_count\n"
        "101,Mechanical Keyboard,Hardware,89.99,15\n"
        "102,Wireless Mouse,Hardware,29.50,40\n"
        "103,Ergonomic Chair,Furniture,249.00,8\n"
        "104,Standing Desk,Furniture,399.00,5\n"
    )


@pytest.fixture
def valid_csv_bytes(valid_csv_content: str) -> bytes:
    """Returns utf-8 encoded bytes of valid CSV data."""
    return valid_csv_content.encode("utf-8")


@pytest.fixture
def valid_csv_file(tmp_path: Path, valid_csv_content: str) -> Path:
    """Creates a temporary valid CSV file on disk."""
    file_path = tmp_path / "test_inventory.csv"
    file_path.write_text(valid_csv_content, encoding="utf-8")
    return file_path


@pytest.fixture
def empty_csv_bytes() -> bytes:
    """Returns empty (0-byte) CSV bytes."""
    return b""


@pytest.fixture
def empty_csv_file(tmp_path: Path) -> Path:
    """Creates a temporary 0-byte CSV file on disk."""
    file_path = tmp_path / "empty_dataset.csv"
    file_path.write_bytes(b"")
    return file_path


@pytest.fixture
def whitespace_csv_bytes() -> bytes:
    """Returns whitespace-only CSV bytes containing no columns or rows."""
    return b"   \n\t  \r\n   \n"


@pytest.fixture
def whitespace_csv_file(tmp_path: Path, whitespace_csv_bytes: bytes) -> Path:
    """Creates a temporary whitespace-only CSV file on disk."""
    file_path = tmp_path / "whitespace_only.csv"
    file_path.write_bytes(whitespace_csv_bytes)
    return file_path


@pytest.fixture
def corrupted_csv_bytes() -> bytes:
    """Returns binary corrupted bytes that cannot be parsed as valid CSV text."""
    return b"\x80\x81\x82\xff\xfe\x00\x00corrupt\xff\xffdata"


@pytest.fixture
def corrupted_csv_file(tmp_path: Path, corrupted_csv_bytes: bytes) -> Path:
    """Creates a temporary corrupted CSV file on disk."""
    file_path = tmp_path / "corrupted_records.csv"
    file_path.write_bytes(corrupted_csv_bytes)
    return file_path


@pytest.fixture
def unsupported_txt_file(tmp_path: Path) -> Path:
    """Creates a temporary file with an unsupported .txt extension."""
    file_path = tmp_path / "plain_document.txt"
    file_path.write_text("This is an unsupported plain text document.", encoding="utf-8")
    return file_path


@pytest.fixture
def unsupported_json_file(tmp_path: Path) -> Path:
    """Creates a temporary file with an unsupported .json extension."""
    file_path = tmp_path / "configuration.json"
    file_path.write_text('{"key": "value"}', encoding="utf-8")
    return file_path


@pytest.fixture
def simple_xlsx_file() -> Path:
    """Returns path to the valid single-sheet Excel workbook fixture."""
    return Path("tests/fixtures/simple_catalog.xlsx")


@pytest.fixture
def multi_sheet_xlsx_file() -> Path:
    """Returns path to the valid complex multi-sheet Excel workbook fixture."""
    return Path("tests/fixtures/multi_sheet_data.xlsx")


@pytest.fixture
def corrupted_xlsx_file() -> Path:
    """Returns path to the corrupted/unreadable Excel workbook fixture."""
    return Path("tests/fixtures/corrupted.xlsx")


