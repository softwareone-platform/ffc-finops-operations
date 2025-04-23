import aiofiles  # type: ignore
import pytest
import time_machine

from app.blob_storage import (
    download_charges_file,
    upload_charges_file,
    validate_year_and_month_format,
)


async def test_can_upload_file():
    async with aiofiles.tempfile.NamedTemporaryFile(suffix=".zip", mode="w") as fakezip:
        await fakezip.write("test")
        await fakezip.flush()
        response = await upload_charges_file(
            file_path=fakezip.name,
            currency="eur",
            year=2025,
            month=3,
        )
    assert response is not None
    assert response == fakezip.name


async def test_cannot_upload_file():
    with pytest.raises(FileNotFoundError, match="not_found"):
        await upload_charges_file(file_path="not_found", currency="eur", year=2025, month=3)


@time_machine.travel("2025-03-20T10:00:00Z", tick=False)
async def test_can_get_a_download_url():
    async with aiofiles.tempfile.NamedTemporaryFile(suffix=".zip", mode="w") as fakezip:
        await fakezip.write("test")
        await fakezip.flush()
        await upload_charges_file(
            file_path=fakezip.name,
            currency="eur",
            year=2025,
            month=3,
        )
        _, filename = fakezip.name.rsplit("/", 1)
        response = await download_charges_file(
            filename=filename, currency="eur", year=2025, month=3
        )
    assert response is not None
    assert f"EUR/2025/03/{filename}" in response


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
