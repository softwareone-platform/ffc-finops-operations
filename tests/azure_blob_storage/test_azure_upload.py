from app.charges_file_azure_storage.upload_file import (
    get_azure_blob_service_client,
    upload_charges_file,
)


def test_ensure_same_instance_of_azureblobserviceclient():
    instance_1 = get_azure_blob_service_client()
    instance_2 = get_azure_blob_service_client()
    assert instance_1 == instance_2


def test_can_upload_file():
    response = upload_charges_file(
        file_path="files_folder/FCHG-1234-5678-9012.zip",
        currency="eur",
        year=2025,
        month=3,
    )
    assert response is not None
    assert response == "files_folder/FCHG-1234-5678-9012.zip"


def test_cannot_upload_file():
    response = upload_charges_file(
        file_path="not_found",
        currency="eur",
        year=2025,
        month=3,
    )
    assert response is None
