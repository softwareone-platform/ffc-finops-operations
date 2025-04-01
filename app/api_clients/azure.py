import logging
from datetime import UTC, datetime, timedelta

import aiofiles
from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    ResourceNotFoundError,
)
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
from azure.storage.blob.aio import ContainerClient

logger = logging.getLogger(__name__)

AZURE_SA_CREDENTIALS = DefaultAzureCredential()


class AsyncAzureBlobServiceClient:
    def __init__(
        self,
        account_url: str,
        container_name: str,
        account_key: str,
        max_block_size: int = 1024 * 1024 * 4,
        max_single_put_size: int = 1024 * 8,
        max_concurrency: int = 4,
        sas_expiration_token_mins: int = 5,
    ):
        self.account_url = account_url
        self.container_name = container_name
        self.account_key = account_key  # the primary access key of the Azure Storage account.
        self.sas_expiration_token_mins = sas_expiration_token_mins

        self.container_client = ContainerClient(
            account_url=self.account_url,
            container_name=self.container_name,
            credential=AZURE_SA_CREDENTIALS,
            max_block_size=max_block_size,
            max_single_put_size=max_single_put_size,
            max_concurrency=max_concurrency,
        )

    async def maybe_create_container(self):
        if not await self.container_client.exists():  # pragma: no branch
            await self.container_client.create_container()
            logger.info(f"Created container {self.container_name}")

    async def __aenter__(self):
        await self.container_client.__aenter__()
        await self.maybe_create_container()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.container_client.__aexit__(exc_type, exc_val, exc_tb)

    async def upload_file_to_azure_blob(
        self,
        blob_name: str,  # the blob name to create or use
        file_path: str,  # Path to the file to upload
    ) -> str | None:
        """
        Uploads a local file to an Azure Blob Storage container.

        This method uploads the specified file to the configured container using
        the provided blob name.

        Args:
            blob_name (str): The name to assign to the blob in Azure Storage.
            file_path (str): The path to the local file to be uploaded.

        Returns:
            str | None: The file path if upload succeeds; otherwise, None.

        """
        blob_client = self.container_client.get_blob_client(blob_name)  # create the blob client

        try:
            logger.debug(f"Trying to Upload {file_path} to Azure Blob Storage {blob_name}")

            async with aiofiles.open(file_path, "rb") as file:
                await blob_client.upload_blob(data=file, overwrite=True)
            logger.info(f"File '{blob_name}' uploaded to container '{self.container_name}'.")
            return file_path
        except FileNotFoundError:
            logger.error(f"The file {file_path} could not be found.")
        except ResourceNotFoundError:  # pragma: no branch
            logger.error(f"Error: The container {self.container_name} does not exist.")
        except AzureError as error:  # pragma: no branch
            logger.error(f"Azure General Error occurred: {error}")
        except ClientAuthenticationError as error:  # pragma: no branch
            logger.error(f"Credentials or SAS token Error occurred: {error}")
        except Exception as error:  # pragma: no branch
            logger.error(f"Unexpected error occurred: {error}")
        return None

    async def get_azure_blob_download_url(self, blob_name: str) -> str:
        """
        Download a blob from Azure Blob Storage using a time-limited SAS token.
        Please note that the function generate_blob_sas() does not raise an exception
        even if you pass an expiry time in the past.
        It just returns a SAS token that is already expired and won't work when used.

        p.s.: If you're using Azurite, make sure you're using the local emulator URL
        with the following format
        http://127.0.0.1:10000/devstoreaccount1/your-container/your-blob
        to download the file, instead of https://devstoreaccount1.blob.core.windows.net/your-container/your-blob
        Args:
            blob_name (str): The name to assign to the blob in Azure Storage.

        Returns:
            str : The url of the file to download. or None if an error occurred.
        """

        blob_client = self.container_client.get_blob_client(blob_name)  # pragma: no branch
        expiry_time = datetime.now(UTC) + timedelta(minutes=self.sas_expiration_token_mins)

        account_name = blob_client.account_name
        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=self.container_name,
            blob_name=blob_name,
            account_key=self.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=expiry_time,
        )
        url = f"https://{account_name}.blob.core.windows.net/{self.container_name}/{blob_name}?{sas_token}"
        return url
