import os

import pytest

from app.blob_storage import (
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
