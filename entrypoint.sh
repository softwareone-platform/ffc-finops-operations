#!/bin/bash

set -e

if [ -z "$FFC_OPERATIONS_AZURE_SA_BLOB_ENDPOINT" ]; then
    export FFC_OPERATIONS_AZURE_SA_BLOB_ENDPOINT="${FFC_OPERATIONS_AZURE_SA_ACCOUNT_NAME}.blob.core.windows.net/"
fi

exec "$@"
