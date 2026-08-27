"""OSS STS token router for frontend uploads."""

import uuid

from fastapi import APIRouter, HTTPException

from app.adapters.oss_adapter import OSSAdapter
from app.exceptions import AudioUploadError

router = APIRouter(prefix="/api/v1/oss", tags=["OSS"])


@router.get("/sts-token")
def get_sts_token():
    """Get STS temporary credentials for frontend upload.

    Frontend uses these credentials to directly upload audio to OSS.

    Returns:
        Response with STS credentials:
        - request_id: Unique request ID
        - data:
            - access_key_id: Temporary AccessKey ID
            - access_key_secret: Temporary AccessKey Secret
            - security_token: Security token
            - expiration: Token expiration time (ISO format)
            - bucket: OSS bucket name
            - region: OSS region

    Raises:
        500: If STS token generation fails
    """
    request_id = str(uuid.uuid4())

    try:
        oss = OSSAdapter()
        token_data = oss.generate_sts_token(duration=3600)  # 1 hour

        return {
            "request_id": request_id,
            "data": token_data,
        }

    except AudioUploadError as e:
        raise HTTPException(
            status_code=500,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "STS_TOKEN_GENERATION_FAILED",
                    "message": str(e),
                },
            },
        )
