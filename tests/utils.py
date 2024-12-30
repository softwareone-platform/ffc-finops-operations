from typing import Any

from app.schemas import BaseSchema


def assert_json_contains_model(json: dict[str, Any], expected_model: BaseSchema) -> None:
    assert all("id" in item for item in json["items"])

    items_by_id = {item["id"]: item for item in json["items"]}

    assert str(expected_model.id) in list(items_by_id.keys())

    expected_dict = expected_model.model_dump(mode="json")
    actual_dict = items_by_id[str(expected_model.id)]

    for key, actual_value in actual_dict.items():
        if key not in expected_dict:
            raise AssertionError(f"{expected_model} has no attribute {key}")

        assert expected_dict[key] == actual_value
