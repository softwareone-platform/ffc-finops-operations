import csv
from contextlib import nullcontext

import pytest
from pydantic import BaseModel, Field
from sqlalchemy_utils.functions.mock import io

from app.utils import PydanticWriter


class RowSchema(BaseModel):
    name: str
    age: int
    email: str = Field(..., serialization_alias="email_address")


@pytest.mark.parametrize(
    ("fieldnames", "expected"),
    [
        (None, ["name", "age", "email"]),
        (["name", "age", "my_email"], ["name", "age", "my_email"]),
        (["name", "age"], ValueError("Invalid number of fieldnames: expected 3, got 2")),
        (
            ["name", "age", "email", "another"],
            ValueError("Invalid number of fieldnames: expected 3, got 4"),
        ),
    ],
)
def test_fieldnames(fieldnames, expected):
    with (
        pytest.raises(expected.__class__, match=str(expected))
        if isinstance(expected, Exception)
        else nullcontext()
    ):
        pydantic_writer = PydanticWriter(RowSchema, io.StringIO(), fieldnames=fieldnames)

        assert pydantic_writer.fieldnames == expected


@pytest.mark.parametrize(
    ("fieldnames", "expected"),
    [
        (None, ["name", "age", "email_address"]),
        (["name", "age", "my_email"], ["name", "age", "email_address"]),
        (["name", "my_age", "my_email"], ["name", "my_age", "email_address"]),
        (["name", "age"], ValueError("Invalid number of fieldnames: expected 3, got 2")),
        (
            ["name", "age", "email", "another"],
            ValueError("Invalid number of fieldnames: expected 3, got 4"),
        ),
    ],
)
def test_headernames(fieldnames, expected):
    with (
        pytest.raises(expected.__class__, match=str(expected))
        if isinstance(expected, Exception)
        else nullcontext()
    ):
        pydantic_writer = PydanticWriter(RowSchema, io.StringIO(), fieldnames=fieldnames)

        assert pydantic_writer.headernames == expected


def test_writerow():
    dict_writer_f = io.StringIO()
    pydantic_writer_f = io.StringIO()

    dict_writer = csv.DictWriter(dict_writer_f, fieldnames=["name", "age", "email"])
    pydantic_writer = PydanticWriter(RowSchema, pydantic_writer_f)

    row = {
        "name": "John Doe",
        "age": 30,
        "email": "john.doe@example.com",
    }

    dict_writer.writerow(row)
    pydantic_writer.writerow(RowSchema(**row))

    dict_writer_f.seek(0)
    pydantic_writer_f.seek(0)

    dict_writer_lines = dict_writer_f.readlines()
    pydantic_writer_lines = pydantic_writer_f.readlines()

    assert dict_writer_lines == pydantic_writer_lines


def test_writerows():
    dict_writer_f = io.StringIO()
    pydantic_writer_f = io.StringIO()

    dict_writer = csv.DictWriter(dict_writer_f, fieldnames=["name", "age", "email"])
    pydantic_writer = PydanticWriter(RowSchema, pydantic_writer_f)

    row_1 = {
        "name": "John Doe",
        "age": 30,
        "email": "john.doe@example.com",
    }
    row_2 = {
        "name": "Jane Doe",
        "age": 25,
        "email": "jane.doe@example.com",
    }

    dict_writer.writerows([row_1, row_2])
    pydantic_writer.writerows([RowSchema(**row_1), RowSchema(**row_2)])

    dict_writer_f.seek(0)
    pydantic_writer_f.seek(0)

    dict_writer_lines = dict_writer_f.readlines()
    pydantic_writer_lines = pydantic_writer_f.readlines()

    assert dict_writer_lines == pydantic_writer_lines


def test_writeheader():
    pydantic_writer_f = io.StringIO()
    pydantic_writer = PydanticWriter(RowSchema, pydantic_writer_f)
    pydantic_writer.writeheader()
    pydantic_writer_f.seek(0)

    assert pydantic_writer_f.readlines() == [
        "name,age,email_address\r\n",
    ]
