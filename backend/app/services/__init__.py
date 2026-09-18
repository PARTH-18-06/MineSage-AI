import boto3
from botocore.config import Config
from redis import Redis

from app.config import settings


def get_redis_client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def get_minio_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.minio_endpoint,
        aws_access_key_id=settings.minio_root_user,
        aws_secret_access_key=settings.minio_root_password,
        use_ssl=settings.minio_secure,
        config=Config(s3={"addressing_style": "path"}),
    )
