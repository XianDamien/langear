"""Sign only authorized MediaAssets; callers never supply storage keys."""
from core.config import get_settings
from core.errors import DomainError


def sign_media(object_key: str) -> str:
    settings = get_settings()
    if not all((settings.oss_access_key_id, settings.oss_access_key_secret, settings.oss_endpoint, settings.oss_bucket_name)):
        raise DomainError(503, "MEDIA_UNAVAILABLE", "Media playback is temporarily unavailable.")
    import oss2
    try:
        endpoint = "https://" + settings.oss_endpoint.removeprefix("https://").removeprefix("http://")
        bucket = oss2.Bucket(oss2.Auth(settings.oss_access_key_id.get_secret_value(), settings.oss_access_key_secret.get_secret_value()), endpoint, settings.oss_bucket_name)
        return bucket.sign_url("GET", object_key, 900)
    except Exception:
        raise DomainError(503, "MEDIA_UNAVAILABLE", "Media playback is temporarily unavailable.") from None
