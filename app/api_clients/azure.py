import logging

from azure.core.exceptions import (
    AzureError,
    ClientAuthenticationError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


AZURE_SA_CREDENTIALS = DefaultAzureCredential()


class AzureBlobServiceClient:
    def __init__(
        self,
        container_name: str,
        connection_string: str | None = None,
    ):
        if connection_string:
            self.blob_service_client = BlobServiceClient(
                account_url=connection_string, credential=AZURE_SA_CREDENTIALS
            )
        else:  # pragma: no branch
            raise ValueError("The connection_string must be provided.")
        self.container_name = container_name

    def get_or_create_container_name(self):
        """
        This method creates or returns the container client
        """
        # Create container if not exists
        try:
            container_client = self.blob_service_client.create_container(self.container_name)
        except ResourceExistsError:
            logger.debug("The Azure storage container already exists. No panic!")
            container_client = self.blob_service_client.get_container_client(self.container_name)
        return container_client

    def upload_file_to_azure_blob(
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
        try:
            logger.debug(f"Uploading {file_path} to Azure Blob Storage {blob_name}")
            self.get_or_create_container_name()
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, blob=blob_name
            )

            with open(file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
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
