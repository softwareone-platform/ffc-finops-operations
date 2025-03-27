import re
from functools import lru_cache

from app.api_clients.azure import AzureBlobServiceClient
from app.conf import get_settings


@lru_cache
def get_azure_blob_service_client() -> AzureBlobServiceClient:
    """
    Return an AzureBlobServiceClient instance.
    the lru_cache allows a single instance of the class.
    """
    settings = get_settings()
    connection_string = settings.azure_sa_url
    container_name = settings.azure_sa_container_name
    return AzureBlobServiceClient(
        connection_string=connection_string, container_name=container_name
    )


def upload_charges_file(
    file_path: str,
    currency: str,
    year: int,
    month: int,
) -> str | None:
    """
    This function is responsible for uploading the given file to Azure Blob Storage.

    Args:
        file_path (str): The path to the file to upload.
        currency (str): The currency of the file.
        year (int): The year of the file.
        month (int): The month of the file.

    Raises (Propagated):
        ValueError: If the format of month and/or year is invalid.
        FileNotFoundError: If the file path does not exist.
        ResourceNotFoundError: If the container does not exist.
        AzureError: If a general error occurs on Azure.
        ClientAuthenticationError: If the authentication error occurs.
        Generic Exception: If the general error occurs.
    """

    filename = file_path.split("/")[-1]
    month, year = validate_year_and_month_format(month, year)

    blob_name = f"{currency.upper()}/{year}/{month}/{filename}"
    azure_client = get_azure_blob_service_client()
    return azure_client.upload_file_to_azure_blob(blob_name=blob_name, file_path=file_path)


def validate_year_and_month_format(month: int, year: int):
    """
    This function ensures that month and year have a valid format.
    Year: from 2025 -> 2999
    Month: cannot be negative, greater than 12.
    A '0' is added as a prefix if month has 1 digit and valid format.
    """
    if month <= 0 or month > 12:
        raise ValueError("Invalid month format.")
    month = int(month)
    if len(str(abs(month))) == 1:
        month = "0" + str(int(month))
    # validate years starting from 2025 to 2999
    pattern = re.compile(r"^20(2[5-9]|[3-9][0-9])$|^2[1-9][0-9]{2}$")
    if not pattern.match(str(year)):
        raise ValueError("Invalid year format.")
    return str(month), str(year)
