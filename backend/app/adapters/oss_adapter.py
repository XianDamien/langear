"""Alibaba Cloud OSS adapter for audio file storage."""

from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import oss2
from aliyunsdkcore.client import AcsClient
from aliyunsdksts.request.v20150401 import AssumeRoleRequest

from app.config import settings
from app.exceptions import AudioUploadError
from app.utils.timezone import app_now


class OSSAdapter:
    """Adapter for Alibaba Cloud OSS (Object Storage Service).

    Handles audio file uploads, URL generation, and STS token management.
    """

    @staticmethod
    def _ensure_https_url(url: str) -> str:
        """Normalize OSS URLs to HTTPS to avoid mixed-content requests."""
        parsed = urlsplit(url)
        if not parsed.scheme:
            return url
        if parsed.scheme == "https":
            return url
        if parsed.scheme == "http":
            return urlunsplit(("https", parsed.netloc, parsed.path, parsed.query, parsed.fragment))
        return url

    def __init__(self):
        """Initialize OSS client with credentials from settings."""
        endpoint = settings.oss_endpoint
        if endpoint.startswith("http://") or endpoint.startswith("https://"):
            endpoint = endpoint.split("//", 1)[1]

        # Normalize region strings.
        # - STS client expects e.g. "cn-shanghai"
        # - OSS endpoint/bucket uses e.g. "oss-cn-shanghai"
        sts_region = settings.oss_region or "cn-shanghai"
        if sts_region.startswith("oss-"):
            sts_region = sts_region[len("oss-") :]

        oss_region = settings.oss_region or "cn-shanghai"
        if not oss_region.startswith("oss-"):
            oss_region = f"oss-{oss_region}"

        self._oss_region = oss_region

        self.auth = oss2.Auth(
            settings.oss_access_key_id,
            settings.oss_access_key_secret,
        )
        self.bucket = oss2.Bucket(
            self.auth,
            endpoint,
            settings.oss_bucket_name,
        )

        # Initialize STS client for temporary credentials
        self.sts_client = AcsClient(
            settings.oss_access_key_id,
            settings.oss_access_key_secret,
            sts_region,
        )

    @property
    def recordings_prefix(self) -> str:
        """Return normalized OSS prefix for user recordings."""
        prefix = (settings.oss_recordings_prefix or "recordings").strip().strip("/")
        return prefix or "recordings"

    def upload_audio(
        self,
        audio_bytes: bytes,
        card_id: int,
        format: str = "wav",
    ) -> str:
        """Upload user recording to OSS.

        Args:
            audio_bytes: Audio file content in bytes
            card_id: Card ID for organizing files
            format: Audio format (default: wav)

        Returns:
            OSS object path (e.g., "recordings/20260208/1001_1707382800.wav")

        Raises:
            AudioUploadError: If upload fails
        """
        try:
            # Generate object path: recordings/{date}/{card_id}_{timestamp}.{format}
            now = app_now()
            date_str = now.strftime("%Y%m%d")
            timestamp = int(now.timestamp())
            object_name = f"{self.recordings_prefix}/{date_str}/{card_id}_{timestamp}.{format}"

            # Upload to OSS
            result = self.bucket.put_object(object_name, audio_bytes)

            # Check if upload was successful
            if result.status != 200:
                raise AudioUploadError(f"OSS returned status {result.status}")

            return object_name

        except Exception as e:
            raise AudioUploadError(str(e))

    def get_url(self, object_name: str, expires: int = 3600) -> str:
        """Generate signed URL for private object access.

        Args:
            object_name: OSS object path
            expires: URL expiration time in seconds (default: 1 hour)

        Returns:
            Signed URL for accessing the object
        """
        return self._ensure_https_url(self.bucket.sign_url("GET", object_name, expires))

    def get_public_url(self, object_name: str) -> str:
        """Get a public-style URL for an object.

        Args:
            object_name: OSS object path

        Returns:
            Configured public URL when available, otherwise a signed URL fallback
        """
        public_base_url = (settings.oss_public_base_url or "").rstrip("/")
        if public_base_url:
            return self._ensure_https_url(f"{public_base_url}/{object_name}")

        return self.generate_signed_url(object_name)

    def generate_sts_token(self, duration: int = 3600) -> dict[str, Any]:
        """Generate STS temporary credentials for frontend upload.

        Uses RAM role AssumeRole to obtain temporary credentials with limited permissions.
        Frontend can use these credentials to directly upload to OSS.

        Args:
            duration: Token validity duration in seconds (default: 1 hour)

        Returns:
            Dictionary containing:
            - access_key_id: Temporary AccessKey ID
            - access_key_secret: Temporary AccessKey Secret
            - security_token: Security token
            - expiration: Expiration time (ISO format)
            - bucket: OSS bucket name
            - region: OSS region

        Raises:
            AudioUploadError: If STS token generation fails
        """
        try:
            role_arn = (settings.aliyun_role_arn or "").strip()
            if not role_arn:
                raise AudioUploadError(
                    "ALIYUN_ROLE_ARN is required for /api/v1/oss/sts-token"
                )

            request = AssumeRoleRequest.AssumeRoleRequest()
            request.set_RoleArn(role_arn)
            request.set_RoleSessionName("langear-frontend-upload")
            request.set_DurationSeconds(duration)

            # Limit permissions to only recordings/ path uploads
            policy = {
                "Version": "1",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": ["oss:PutObject", "oss:GetObject"],
                        "Resource": [
                            f"acs:oss:*:*:{settings.oss_bucket_name}/{self.recordings_prefix}/*"
                        ],
                    }
                ],
            }
            import json

            request.set_Policy(json.dumps(policy))

            response = self.sts_client.do_action_with_exception(request)
            response_data = json.loads(response)

            credentials = response_data["Credentials"]
            expiration_time = datetime.fromisoformat(
                credentials["Expiration"].replace("Z", "+00:00")
            )

            return {
                "access_key_id": credentials["AccessKeyId"],
                "access_key_secret": credentials["AccessKeySecret"],
                "security_token": credentials["SecurityToken"],
                "expiration": expiration_time.isoformat(),
                "bucket": settings.oss_bucket_name,
                "region": self._oss_region,
                "upload_prefix": self.recordings_prefix,
            }

        except AudioUploadError:
            raise
        except Exception as e:
            raise AudioUploadError(f"Failed to generate STS token: {str(e)}")

    def generate_signed_url(
        self, object_name: str, expires: int = 3600, method: str = "GET"
    ) -> str:
        """Generate signed URL for temporary object access (used for ASR).

        Args:
            object_name: OSS object path
            expires: URL expiration time in seconds (default: 1 hour)
            method: HTTP method (GET or PUT)

        Returns:
            Signed URL for accessing the object
        """
        return self._ensure_https_url(self.bucket.sign_url(method, object_name, expires))

    def upload_file_from_path(
        self,
        local_path: str,
        object_path: str,
    ) -> bool:
        """Upload local file to OSS.

        Args:
            local_path: Local file path
            object_path: OSS object path (e.g., "lessons/NCE2/01-03/file.mp3")

        Returns:
            True if upload successful, False otherwise
        """
        try:
            with open(local_path, "rb") as f:
                audio_bytes = f.read()

            result = self.bucket.put_object(object_path, audio_bytes)
            return result.status == 200
        except Exception:
            return False

    def batch_upload_files(
        self,
        files: list[tuple[str, str]],
        max_workers: int = 10,
    ) -> dict[str, bool]:
        """Upload multiple files concurrently to OSS.

        Args:
            files: List of (local_path, object_path) tuples
            max_workers: Maximum number of concurrent uploads

        Returns:
            Dictionary mapping object_path to success status
        """
        from concurrent.futures import ThreadPoolExecutor

        results = {}

        def upload_single(local_path: str, object_path: str) -> tuple[str, bool]:
            success = self.upload_file_from_path(local_path, object_path)
            return object_path, success

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(upload_single, local_path, object_path)
                for local_path, object_path in files
            ]
            for future in futures:
                object_path, success = future.result()
                results[object_path] = success

        return results
