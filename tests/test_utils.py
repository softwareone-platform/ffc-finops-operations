from datetime import UTC, datetime

import jwt
from freezegun import freeze_time

from app import settings
from app.constants import (
    API_MODIFIER_JWT_ALGORITHM,
    API_MODIFIER_JWT_AUDIENCE,
    API_MODIFIER_JWT_EXPIRE_AFTER_SECONDS,
    API_MODIFIER_JWT_ISSUER,
)
from app.utils import get_api_modifier_jwt_token


@freeze_time("2024-01-01T00:00:00Z")
def test_get_api_modifier_jwt_token(mock_settings: None):
    token = get_api_modifier_jwt_token()
    decoded_token = jwt.decode(
        token,
        settings.api_modifier_jwt_secret,
        audience=API_MODIFIER_JWT_AUDIENCE,
        algorithms=[API_MODIFIER_JWT_ALGORITHM],
    )
    assert decoded_token["iss"] == API_MODIFIER_JWT_ISSUER
    assert decoded_token["aud"] == API_MODIFIER_JWT_AUDIENCE

    timestamp = int(datetime.now(UTC).timestamp())

    assert decoded_token["iat"] == timestamp
    assert decoded_token["nbf"] == timestamp
    assert decoded_token["exp"] == timestamp + API_MODIFIER_JWT_EXPIRE_AFTER_SECONDS
