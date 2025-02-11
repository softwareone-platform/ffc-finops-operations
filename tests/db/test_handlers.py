import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.handlers import (
    ConstraintViolationError,
    ModelHandler,
    NotFoundError,
)
from tests.db.models import ModelForTests, ParentModelForTests


class Model4TestsHandler(ModelHandler[ModelForTests]):
    pass


async def test_create_success(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    test_obj = ModelForTests(name="Test Object")

    created_obj = await handler.create(test_obj)

    assert created_obj.id is not None
    assert created_obj.id.startswith(ModelForTests.PK_PREFIX)
    assert created_obj.name == "Test Object"


async def test_create_constraint_violation(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    obj1 = ModelForTests(name="Duplicate Name")
    await handler.create(obj1)

    obj2 = ModelForTests(name="Duplicate Name")

    with pytest.raises(ConstraintViolationError):
        await handler.create(obj2)


async def test_get_success(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    test_obj = ModelForTests(name="Get Test Object")
    await handler.create(test_obj)

    fetched_obj = await handler.get(test_obj.id)
    assert fetched_obj.id == test_obj.id
    assert fetched_obj.name == "Get Test Object"


async def test_get_not_found(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)

    with pytest.raises(NotFoundError):
        await handler.get("not-found")


async def test_update_success(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    test_obj = ModelForTests(name="Update Test Object")
    created_obj = await handler.create(test_obj)

    updated_obj = await handler.update(created_obj.id, {"name": "Updated Name"})
    assert updated_obj.name == "Updated Name"


async def test_fetch_page(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)

    # Create multiple objects
    for i in range(5):
        await handler.create(ModelForTests(name=f"Object {i}"))

    results = await handler.fetch_page(limit=3, offset=1)
    assert len(results) == 3


async def test_count(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    for i in range(5):
        await handler.create(ModelForTests(name=f"Object {i}"))
    count = await handler.count()
    assert count == 5


async def test_filter(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    for i in range(5):
        await handler.create(ModelForTests(name=f"Object {i}"))
    results = await handler.filter(ModelForTests.name.like("Object%"))

    assert len(results) == 5


async def test_first(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    for i in range(5):
        await handler.create(ModelForTests(name=f"Object {i}"))
    first_result = await handler.first(ModelForTests.name.like("Object%"))

    assert first_result is not None
    assert first_result.name.startswith("Object")


async def test_fetch_page_extra_conditions(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    test_obj1 = ModelForTests(name="Condition Test 1", status="inactive")
    test_obj2 = ModelForTests(name="Condition Test 2", status="active")

    await handler.create(test_obj1)
    await handler.create(test_obj2)

    # Fetch with extra condition to only get active status
    results = await handler.fetch_page(extra_conditions=[ModelForTests.status == "active"])
    assert len(results) == 1
    assert results[0].name == "Condition Test 2"


async def test_get_extra_conditions(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    test_obj1 = ModelForTests(name="Condition Test 1", status="inactive")
    test_obj2 = ModelForTests(name="Condition Test 2", status="active")

    await handler.create(test_obj1)
    await handler.create(test_obj2)

    # Fetch with extra condition to only get active status
    result = await handler.get(test_obj2.id, extra_conditions=[ModelForTests.status == "active"])
    assert result == test_obj2


async def test_get_default_options_with_joinedload(db_session: AsyncSession):
    parent_obj = ParentModelForTests(description="Parent Description")
    db_session.add(parent_obj)
    await db_session.commit()
    handler = Model4TestsHandler(db_session)
    handler.default_options = [joinedload(ModelForTests.parent)]
    test_obj = ModelForTests(name="With Related")
    test_obj.parent = parent_obj
    await handler.create(test_obj)
    db_session.expunge_all()

    fetched_obj = await handler.get(test_obj.id)
    assert fetched_obj.parent.description == "Parent Description"


async def test_count_with_extra_conditions(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)

    await handler.create(ModelForTests(name="Object 1", status="inactive"))
    await handler.create(ModelForTests(name="Object 2", status="active"))

    count_active = await handler.count(ModelForTests.status == "active")
    assert count_active == 1


async def test_filter_with_default_load_options(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    parent = ParentModelForTests(description="Parent Description")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    model = ModelForTests(name="Test Object", parent=parent)
    await handler.create(model)

    handler.default_options = [joinedload(ModelForTests.parent)]
    results = await handler.filter(ModelForTests.name == "Test Object")
    assert len(results) == 1
    assert results[0].parent.description == "Parent Description"


async def test_first_with_default_load_options(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    parent = ParentModelForTests(description="First Parent Description")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    model = ModelForTests(name="First Test Object", parent=parent)
    await handler.create(model)

    handler.default_options = [joinedload(ModelForTests.parent)]
    first_result = await handler.first(ModelForTests.name == "First Test Object")
    assert first_result is not None
    assert first_result.parent.description == "First Parent Description"


async def test_get_or_create_with_default_load_options(db_session: AsyncSession):
    handler = Model4TestsHandler(db_session)
    parent = ParentModelForTests(description="GetOrCreate Parent")
    db_session.add(parent)
    await db_session.commit()
    await db_session.refresh(parent)

    handler.default_options = [joinedload(ModelForTests.parent)]

    obj, created = await handler.get_or_create(
        defaults={"parent_id": parent.id}, name="GetOrCreate Object"
    )
    assert created is True
    assert obj.parent.description == "GetOrCreate Parent"

    # Ensure fetching without creation
    obj, created = await handler.get_or_create(
        defaults={"parent_id": parent.id}, name="GetOrCreate Object"
    )
    assert created is False
    assert obj.parent.description == "GetOrCreate Parent"
