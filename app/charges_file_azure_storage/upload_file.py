from functools import lru_cache

from app.charges_file_azure_storage.services.azure_container import AzureBlobServiceClient

# from app.conf import get_settings

AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)


@lru_cache
def get_azure_blob_service_client(
    connection_string: str | None = None, container_name: str | None = None
) -> AzureBlobServiceClient:
    connection_string = connection_string or AZURITE_CONNECTION_STRING
    container_name = container_name or "charges-file"
    return AzureBlobServiceClient(
        connection_string=connection_string, container_name=container_name
    )


def upload_charges_file(file_path: str, currency: str, year: int, month: int) -> str | None:
    filename = file_path.split("/")[-1]
    blob_name = f"{currency.upper()}/{year}/{month}/{filename}"
    azure_client = get_azure_blob_service_client()
    return azure_client.upload_file_to_azure_blob(blob_name=blob_name, file_path=file_path)
