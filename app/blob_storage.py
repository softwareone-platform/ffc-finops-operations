from app.api_clients.azure import AsyncAzureBlobServiceClient
from app.conf import get_settings


async def upload_charges_file(
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
    settings = get_settings()
    azure_client = AsyncAzureBlobServiceClient(
        account_url=settings.azure_sa_url,
        container_name=settings.azure_sa_container_name,
        max_concurrency=settings.azure_sa_max_concurrency,
        max_single_put_size=settings.azure_sa_max_single_put_size,
        max_block_size=settings.azure_sa_max_block_size,
    )
    async with azure_client:
        return await azure_client.upload_file_to_azure_blob(
            blob_name=blob_name, file_path=file_path
        )


def validate_year_and_month_format(month: int, year: int):
    """
    This function ensures that month and year have a valid format.
    Year: from 1970
    Month: cannot be negative, greater than 12.
    A '0' is added as a prefix if month has 1 digit and valid format.
    """
    if month <= 0 or month > 12:
        raise ValueError("Invalid month format.")
    month = int(month)  # to ensure floats will be addressed
    month = f"{month:02}"
    if year < 1970:
        raise ValueError("Invalid year format.")
    return str(month), str(year)
