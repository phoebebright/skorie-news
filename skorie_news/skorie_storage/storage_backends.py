from __future__ import annotations
import io
import time
from contextlib import contextmanager

import boto3
from django.conf import settings
from django.core.cache import cache
from django.utils.crypto import salted_hmac
from storages.backends.s3boto3 import S3Boto3Storage


# ---------- Base private S3 storage variants ----------

class _BasePrivateS3(S3Boto3Storage):
    default_acl = "private"
    querystring_auth = True
    querystring_expire = 3600
    custom_domain = None  # signed URLs via endpoint

    def __init__(
        self,
        *,
        bucket_name: str,
        endpoint_url: str,
        region_name: str,
        location: str,
        access_key_id: str,
        secret_access_key: str,
        url_expire: int,
        file_overwrite: bool = False,
        **kwargs,
    ):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self.querystring_expire = int(url_expire)
        self.location = location
        self.file_overwrite = file_overwrite
        # Configure boto3 session for this backend
        self._session = boto3.session.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name,
        )
        super().__init__(**kwargs)

    @property
    def connection(self):
        # override to bind to our endpoint/session
        return self._session.resource("s3", endpoint_url=self.endpoint_url)

    @property
    def client(self):
        return self._session.client("s3", endpoint_url=self.endpoint_url)


class HetznerPrivateStorage(_BasePrivateS3):
    def __init__(self, **kwargs):
        super().__init__(
            bucket_name=settings.HETZNER_AWS_STORAGE_BUCKET_NAME,
            endpoint_url=settings.HETZNER_AWS_S3_ENDPOINT_URL,
            region_name=settings.HETZNER_AWS_S3_REGION_NAME,
            access_key_id=settings.HETZNER_AWS_ACCESS_KEY_ID,
            secret_access_key=settings.HETZNER_AWS_SECRET_ACCESS_KEY,
            addressing_style=settings.HETZNER_AWS_S3_ADDRESSING_STYLE,
            signature_version=settings.HETZNER_AWS_S3_SIGNATURE_VERSION,
            location = settings.HETZNER_AWS_S3_LOCATION,
            file_overwrite = settings.HETZNER_AWS_S3_FILE_OVERWRITE,
            url_expire=getattr(settings, "HETZNER_URL_EXPIRE_SECONDS", 3600),
            **kwargs,
        )


class _BasePublicS3(S3Boto3Storage):
    default_acl = "public-read"
    querystring_auth = False        # no presigned URLs
    custom_domain = None            # use endpoint URL
    file_overwrite = False

    def __init__(
        self,
        *,
        bucket_name: str,
        endpoint_url: str,
        region_name: str,
        location: str,
        access_key_id: str,
        secret_access_key: str,
        file_overwrite: bool = False,
        url_expire: int | None = None,
        **kwargs,
    ):
        self.bucket_name = bucket_name
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self.location = location
        self.file_overwrite = file_overwrite
        self.url_expire = url_expire

        # Configure boto3 session for this backend
        self._session = boto3.session.Session(
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name,
        )
        super().__init__(**kwargs)

    @property
    def connection(self):
        # bind to the Hetzner endpoint
        return self._session.resource("s3", endpoint_url=self.endpoint_url)

    @property
    def client(self):
        return self._session.client("s3", endpoint_url=self.endpoint_url)

class HetznerPublicStorage(_BasePublicS3):
    def __init__(self, **kwargs):
        super().__init__(
            bucket_name=settings.HETZNER_AWS_STORAGE_PUBLIC_BUCKET,
            endpoint_url=settings.HETZNER_AWS_S3_ENDPOINT_URL,
            region_name=settings.HETZNER_AWS_S3_REGION_NAME,
            access_key_id=settings.HETZNER_AWS_ACCESS_KEY_ID,
            secret_access_key=settings.HETZNER_AWS_SECRET_ACCESS_KEY,
            addressing_style=settings.HETZNER_AWS_S3_ADDRESSING_STYLE,
            signature_version=settings.HETZNER_AWS_S3_SIGNATURE_VERSION,
            location=settings.HETZNER_AWS_S3_LOCATION,  # 'ride'
            file_overwrite=False,
            url_expire=getattr(settings, "HETZNER_PUBLIC_URL_EXPIRE_SECONDS", None),
            **kwargs,
        )
