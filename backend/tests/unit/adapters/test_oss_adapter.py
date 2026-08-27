"""Unit tests for OSS adapter.

Tests cover:
- Audio file upload
- Signed URL generation
- Public URL compatibility fallback
- STS token generation

All tests use mocks to avoid real Aliyun OSS API calls.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
from app.adapters.oss_adapter import OSSAdapter
from app.exceptions import AudioUploadError


@pytest.mark.unit
class TestOSSAdapter:
    """Test suite for OSSAdapter."""

    @pytest.fixture
    def oss_adapter(self):
        """Create OSSAdapter instance with mocked OSS clients."""
        with patch("app.adapters.oss_adapter.oss2.Auth") as mock_auth, \
             patch("app.adapters.oss_adapter.oss2.Bucket") as mock_bucket, \
             patch("app.adapters.oss_adapter.AcsClient") as mock_acs_client:

            adapter = OSSAdapter()
            adapter.bucket = mock_bucket.return_value
            adapter.sts_client = mock_acs_client.return_value

            yield adapter

    def test_upload_audio_success(self, oss_adapter):
        """Test successful audio upload to OSS."""
        # Arrange
        audio_bytes = b"fake audio data"
        card_id = 1001
        format = "wav"

        # Mock successful upload response
        mock_result = Mock()
        mock_result.status = 200
        oss_adapter.bucket.put_object = Mock(return_value=mock_result)

        # Act
        with patch("app.adapters.oss_adapter.app_now") as mock_now:
            mock_now.return_value = datetime(2026, 2, 8, 15, 30, 45)
            object_name = oss_adapter.upload_audio(audio_bytes, card_id, format)

        # Assert
        assert object_name.startswith("recordings/")
        assert str(card_id) in object_name
        assert object_name.endswith(f".{format}")

        # Verify put_object was called with correct arguments
        oss_adapter.bucket.put_object.assert_called_once()
        call_args = oss_adapter.bucket.put_object.call_args
        assert call_args[0][1] == audio_bytes

    def test_upload_audio_failure(self, oss_adapter):
        """Test audio upload failure handling."""
        # Arrange
        audio_bytes = b"fake audio data"
        card_id = 1001

        # Mock failed upload response
        mock_result = Mock()
        mock_result.status = 500
        oss_adapter.bucket.put_object = Mock(return_value=mock_result)

        # Act & Assert
        with pytest.raises(AudioUploadError) as exc_info:
            oss_adapter.upload_audio(audio_bytes, card_id)

        assert "OSS returned status 500" in str(exc_info.value)

    def test_upload_audio_exception(self, oss_adapter):
        """Test audio upload with exception."""
        # Arrange
        audio_bytes = b"fake audio data"
        card_id = 1001

        # Mock exception during upload
        oss_adapter.bucket.put_object = Mock(side_effect=Exception("Network error"))

        # Act & Assert
        with pytest.raises(AudioUploadError) as exc_info:
            oss_adapter.upload_audio(audio_bytes, card_id)

        assert "Network error" in str(exc_info.value)

    def test_get_url(self, oss_adapter):
        """Test signed URL generation with default expiration."""
        # Arrange
        object_name = "recordings/20260208/1001_1707382800.wav"
        expected_url = f"https://test-bucket.oss-cn-shanghai.aliyuncs.com/{object_name}?signed=true"

        oss_adapter.bucket.sign_url = Mock(return_value=expected_url)

        # Act
        url = oss_adapter.get_url(object_name)

        # Assert
        assert url == expected_url
        oss_adapter.bucket.sign_url.assert_called_once_with("GET", object_name, 3600)

    def test_get_url_custom_expiration(self, oss_adapter):
        """Test signed URL generation with custom expiration."""
        # Arrange
        object_name = "recordings/20260208/1001_1707382800.wav"
        expires = 7200  # 2 hours
        expected_url = f"https://test-bucket.oss-cn-shanghai.aliyuncs.com/{object_name}?signed=true"

        oss_adapter.bucket.sign_url = Mock(return_value=expected_url)

        # Act
        url = oss_adapter.get_url(object_name, expires=expires)

        # Assert
        assert url == expected_url
        oss_adapter.bucket.sign_url.assert_called_once_with("GET", object_name, expires)

    def test_get_public_url(self, oss_adapter):
        """Test configured public base URL generation for lesson audio."""
        # Arrange
        object_name = "lessons/beginner/lesson1.mp3"

        with patch("app.adapters.oss_adapter.settings") as mock_settings:
            mock_settings.oss_public_base_url = "https://cdn.langear.com"

            # Act
            url = oss_adapter.get_public_url(object_name)

        # Assert
        assert url == f"https://cdn.langear.com/{object_name}"

    def test_get_public_url_upgrades_http_base_url(self, oss_adapter):
        """Configured public HTTP URLs should be normalized to HTTPS."""
        object_name = "lessons/beginner/lesson1.mp3"

        with patch("app.adapters.oss_adapter.settings") as mock_settings:
            mock_settings.oss_public_base_url = "http://cdn.langear.com"

            url = oss_adapter.get_public_url(object_name)

        assert url == f"https://cdn.langear.com/{object_name}"

    def test_get_public_url_falls_back_to_signed_url(self, oss_adapter):
        """When no public base is configured, fall back to a signed URL."""
        object_name = "lessons/beginner/lesson1.mp3"
        oss_adapter.bucket.sign_url = Mock(return_value="https://signed.example.com/audio")

        with patch("app.adapters.oss_adapter.settings") as mock_settings:
            mock_settings.oss_public_base_url = None

            url = oss_adapter.get_public_url(object_name)

        assert url == "https://signed.example.com/audio"
        oss_adapter.bucket.sign_url.assert_called_once_with("GET", object_name, 3600)

    def test_generate_sts_token_success(self, oss_adapter):
        """Test successful STS token generation."""
        # Arrange
        mock_response = {
            "Credentials": {
                "AccessKeyId": "STS.MockAccessKeyId123",
                "AccessKeySecret": "MockAccessKeySecret456",
                "SecurityToken": "MockSecurityToken789",
                "Expiration": "2026-02-08T16:30:45Z"
            }
        }

        oss_adapter.sts_client.do_action_with_exception = Mock(
            return_value='{"Credentials": {"AccessKeyId": "STS.MockAccessKeyId123", '
                        '"AccessKeySecret": "MockAccessKeySecret456", '
                        '"SecurityToken": "MockSecurityToken789", '
                        '"Expiration": "2026-02-08T16:30:45Z"}}'
        )

        with patch("app.adapters.oss_adapter.settings") as mock_settings:
            mock_settings.aliyun_role_arn = "acs:ram::123456:role/langear-oss-upload"
            mock_settings.oss_bucket_name = "langear-dev"
            mock_settings.oss_region = "oss-cn-shanghai"
            mock_settings.oss_recordings_prefix = "recordings"

            # Act
            token = oss_adapter.generate_sts_token()

        # Assert
        assert token["access_key_id"] == "STS.MockAccessKeyId123"
        assert token["access_key_secret"] == "MockAccessKeySecret456"
        assert token["security_token"] == "MockSecurityToken789"
        assert token["bucket"] == "langear-dev"
        assert token["region"] == "oss-cn-shanghai"
        assert token["upload_prefix"] == "recordings"
        assert "expiration" in token

        # Verify the request was made with correct parameters
        oss_adapter.sts_client.do_action_with_exception.assert_called_once()

    def test_generate_sts_token_requires_aliyun_role_arn(self, oss_adapter):
        """Test STS token generation fails clearly when role ARN is missing."""
        with patch("app.adapters.oss_adapter.settings") as mock_settings:
            mock_settings.aliyun_role_arn = None

            with pytest.raises(AudioUploadError) as exc_info:
                oss_adapter.generate_sts_token()

        assert "ALIYUN_ROLE_ARN is required" in str(exc_info.value)

    def test_generate_sts_token_custom_duration(self, oss_adapter):
        """Test STS token generation with custom duration."""
        # Arrange
        duration = 7200  # 2 hours
        mock_response = '{"Credentials": {"AccessKeyId": "STS.Test", ' \
                       '"AccessKeySecret": "Secret", ' \
                       '"SecurityToken": "Token", ' \
                       '"Expiration": "2026-02-08T18:30:45Z"}}'

        oss_adapter.sts_client.do_action_with_exception = Mock(return_value=mock_response)

        with patch("app.adapters.oss_adapter.settings") as mock_settings, \
             patch("app.adapters.oss_adapter.AssumeRoleRequest.AssumeRoleRequest") as mock_request_class:

            mock_settings.aliyun_role_arn = "acs:ram::123456:role/test"
            mock_settings.oss_bucket_name = "test-bucket"
            mock_settings.oss_region = "oss-cn-shanghai"
            mock_settings.oss_recordings_prefix = "recordings"

            mock_request = MagicMock()
            mock_request_class.return_value = mock_request

            # Act
            token = oss_adapter.generate_sts_token(duration=duration)

        # Assert
        assert "access_key_id" in token
        # Verify duration was set correctly
        mock_request.set_DurationSeconds.assert_called_once_with(duration)

    def test_generate_sts_token_failure(self, oss_adapter):
        """Test STS token generation failure handling."""
        # Arrange
        oss_adapter.sts_client.do_action_with_exception = Mock(
            side_effect=Exception("STS service unavailable")
        )

        with patch("app.adapters.oss_adapter.settings") as mock_settings:
            mock_settings.aliyun_role_arn = "acs:ram::123456:role/test"
            mock_settings.oss_bucket_name = "test-bucket"
            mock_settings.oss_recordings_prefix = "recordings"

            # Act & Assert
            with pytest.raises(AudioUploadError) as exc_info:
                oss_adapter.generate_sts_token()

            assert "Failed to generate STS token" in str(exc_info.value)

    def test_generate_signed_url_get_method(self, oss_adapter):
        """Test signed URL generation for GET requests."""
        # Arrange
        object_name = "recordings/test.wav"
        expected_url = "https://bucket.oss.com/recordings/test.wav?signed=true"

        oss_adapter.bucket.sign_url = Mock(return_value=expected_url)

        # Act
        url = oss_adapter.generate_signed_url(object_name, expires=3600, method="GET")

        # Assert
        assert url == expected_url
        oss_adapter.bucket.sign_url.assert_called_once_with("GET", object_name, 3600)

    def test_generate_signed_url_upgrades_http_to_https(self, oss_adapter):
        """Signed OSS URLs should always be returned as HTTPS."""
        object_name = "recordings/test.wav"
        oss_adapter.bucket.sign_url = Mock(
            return_value="http://bucket.oss.com/recordings/test.wav?signed=true"
        )

        url = oss_adapter.generate_signed_url(object_name, expires=3600, method="GET")

        assert url == "https://bucket.oss.com/recordings/test.wav?signed=true"

    def test_generate_signed_url_put_method(self, oss_adapter):
        """Test signed URL generation for PUT requests (upload)."""
        # Arrange
        object_name = "recordings/new_file.wav"
        expected_url = "https://bucket.oss.com/recordings/new_file.wav?signed=true"

        oss_adapter.bucket.sign_url = Mock(return_value=expected_url)

        # Act
        url = oss_adapter.generate_signed_url(object_name, expires=1800, method="PUT")

        # Assert
        assert url == expected_url
        oss_adapter.bucket.sign_url.assert_called_once_with("PUT", object_name, 1800)

    def test_upload_audio_object_name_format(self, oss_adapter):
        """Test that uploaded audio files follow correct naming convention."""
        # Arrange
        audio_bytes = b"test audio"
        card_id = 9999

        mock_result = Mock()
        mock_result.status = 200
        oss_adapter.bucket.put_object = Mock(return_value=mock_result)

        # Act
        with patch("app.adapters.oss_adapter.app_now") as mock_now:
            mock_now.return_value = datetime(2026, 2, 8, 10, 20, 30)
            object_name = oss_adapter.upload_audio(audio_bytes, card_id, "mp3")

        # Assert - verify format: recordings/{YYYYMMDD}/{card_id}_{timestamp}.{format}
        parts = object_name.split("/")
        assert len(parts) == 3
        assert parts[0] == "recordings"
        assert parts[1] == "20260208"  # Date part
        assert parts[2].startswith(f"{card_id}_")
        assert parts[2].endswith(".mp3")

    def test_generate_sts_token_uses_custom_upload_prefix(self, oss_adapter):
        """STS token response and policy should follow custom upload prefix."""
        oss_adapter.sts_client.do_action_with_exception = Mock(
            return_value='{"Credentials": {"AccessKeyId": "STS.Test", '
            '"AccessKeySecret": "Secret", '
            '"SecurityToken": "Token", '
            '"Expiration": "2026-02-08T18:30:45Z"}}'
        )

        with patch("app.adapters.oss_adapter.settings") as mock_settings:
            mock_settings.aliyun_role_arn = "acs:ram::123456:role/test"
            mock_settings.oss_bucket_name = "test-bucket"
            mock_settings.oss_region = "oss-cn-shanghai"
            mock_settings.oss_recordings_prefix = "test/recordings"

            token = oss_adapter.generate_sts_token()

        assert token["upload_prefix"] == "test/recordings"

    def test_upload_audio_honors_custom_prefix(self, oss_adapter):
        """Uploaded audio path should follow configured recordings prefix."""
        audio_bytes = b"test audio"
        card_id = 9999

        mock_result = Mock()
        mock_result.status = 200
        oss_adapter.bucket.put_object = Mock(return_value=mock_result)

        with patch("app.adapters.oss_adapter.settings") as mock_settings, \
             patch("app.adapters.oss_adapter.app_now") as mock_now:
            mock_settings.oss_recordings_prefix = "test/recordings"
            mock_now.return_value = datetime(2026, 2, 8, 10, 20, 30)
            object_name = oss_adapter.upload_audio(audio_bytes, card_id, "mp3")

        assert object_name.startswith("test/recordings/20260208/")
