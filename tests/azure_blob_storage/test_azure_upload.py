import os
from urllib.parse import urlparse

import pytest
import time_machine

from app.blob_storage import (
    download_charges_file,
    upload_charges_file,
    validate_year_and_month_format,
)


async def test_can_upload_file():
    zip_file_path = os.path.join(os.path.dirname(__file__), "files_folder/FCHG-1234-5678-9012.zip")
    response = await upload_charges_file(
        file_path=zip_file_path,
        currency="eur",
        year=2025,
        month=3,
    )
    assert response is not None
    assert response == zip_file_path


async def test_cannot_upload_file():
    response = await upload_charges_file(
        file_path="not_found",
        currency="eur",
        year=2025,
        month=3,
    )
    assert response is None


@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
async def test_can_get_a_download_url():
    zip_file_path = os.path.join(os.path.dirname(__file__), "files_folder/FCHG-1234-5678-9012.zip")
    filename = zip_file_path.split("/")[-1]
    response = await download_charges_file(filename=filename, currency="eur", year=2025, month=3)
    assert response is not None
    assert isinstance(response, str)
    url_parsed = urlparse(response)
    path_parts = url_parsed.path.lstrip("/").split("/")
    blob_name = "/".join(path_parts[1:])
    assert blob_name == "EUR/2025/03/FCHG-1234-5678-9012.zip"


def test_validate_year_and_month_format():
    month, year = validate_year_and_month_format(month=1, year=2025)
    assert month == "01"
    assert year == "2025"


def test_validate_year_and_month_float_format():
    month, year = validate_year_and_month_format(month=1.2, year=2025)  # type: ignore
    assert month == "01"
    assert year == "2025"


def test_validate_year_and_month_format_2():
    month, year = validate_year_and_month_format(month=12, year=2025)
    assert month == "12"
    assert year == "2025"


def test_validate_year_and_month_format_with_wrong_format():
    with pytest.raises(ValueError) as excinfo:
        validate_year_and_month_format(month=30, year=1000)
    assert "Invalid month format." in str(excinfo.value)


def test_validate_year_and_month_format_with_negative_month():
    with pytest.raises(ValueError) as excinfo:
        validate_year_and_month_format(month=-10, year=2025)
    assert "Invalid month format." in str(excinfo.value)


def test_validate_year_and_month_format_with_not_valid_year():
    with pytest.raises(ValueError) as excinfo:
        validate_year_and_month_format(month=10, year=1960)
    assert "Invalid year format." in str(excinfo.value)
