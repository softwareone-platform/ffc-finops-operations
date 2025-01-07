from typing import Any

from app.schemas import BaseReadSchema


def assert_json_contains_model(json: dict[str, Any], expected_schema: BaseReadSchema) -> None:
    assert all("id" in item for item in json["items"])

    items_by_id = {item["id"]: item for item in json["items"]}

    assert str(expected_schema.id) in list(items_by_id.keys())

    expected_dict = expected_schema.model_dump(mode="json")
    actual_dict = items_by_id[str(expected_schema.id)]

    for key, actual_value in actual_dict.items():
        if key not in expected_dict:
            raise AssertionError(f"{expected_schema} has no attribute {key}")

        assert expected_dict[key] == actual_value
