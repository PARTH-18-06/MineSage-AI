from io import BytesIO

from fastapi import UploadFile

from app.config import settings
from app.services import get_minio_client


def upload_file(file: UploadFile, object_path: str) -> int:
    client = get_minio_client()
    content = file.file.read()
    client.put_object(
        Bucket=settings.minio_bucket,
        Key=object_path,
        Body=BytesIO(content),
        ContentLength=len(content),
        ContentType=file.content_type or "application/octet-stream",
    )
    return len(content)


def download_file(object_path: str) -> bytes:
    client = get_minio_client()
    response = client.get_object(Bucket=settings.minio_bucket, Key=object_path)
    try:
        return response["Body"].read()
    finally:
        response["Body"].close()


def object_exists(object_path: str) -> bool:
    client = get_minio_client()
    client.head_object(Bucket=settings.minio_bucket, Key=object_path)
    return True
