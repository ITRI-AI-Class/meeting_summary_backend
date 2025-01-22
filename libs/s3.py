import os
import boto3
import json
from botocore.exceptions import ClientError
class S3:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(S3, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        S3_ENDPOINT = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
        S3_ACCESS_KEY = os.environ.get("S3_ACCESS_KEY", "minioadmin")
        S3_SECRET_KEY = os.environ.get("S3_SECRET_KEY", "minioadmin")
        AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

        self.S3_BUCKET = os.environ.get("S3_BUCKET", "openvidu")
        self.s3_client = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            region_name=AWS_REGION
        )

    def exists(self, key):
        try:
            self.head_object(key)
            return True
        except ClientError:
            return False

    def head_object(self, key):
        params = {
            'Bucket': self.S3_BUCKET,
            'Key': key
        }
        return self.s3_client.head_object(**params)

    def get_object_size(self, key):
        response = self.head_object(key)
        return response.get('ContentLength')

    def get_object(self, key, range_start=None, range_end=None):
        params = {
            'Bucket': self.S3_BUCKET,
            'Key': key
        }
        if range_start is not None and range_end is not None:
            params['Range'] = f'bytes={range_start}-{range_end}'

        response = self.s3_client.get_object(**params)
        return response['Body']

    def get_object_as_json(self, key):
        body = self.get_object(key)
        stringified_data = body.read().decode('utf-8')
        return json.loads(stringified_data)

    def list_objects(self, prefix='', regex=None):
        import re
        params = {
            'Bucket': self.S3_BUCKET,
            'Prefix': prefix
        }
        response = self.s3_client.list_objects_v2(**params)
        objects = response.get('Contents', [])

        if regex:
            pattern = re.compile(regex)
            return [obj['Key'] for obj in objects if pattern.match(obj['Key'])]

        return [obj['Key'] for obj in objects]

    def upload_object(self, key, file):
        params = {
            'Bucket': self.S3_BUCKET,
            'Key': key,
            'Fileobj': file,
        }
        return self.s3_client.upload_fileobj(**params)

    def download_object(self, key, file):
        params = {
            'Bucket': self.S3_BUCKET,
            'Key': key,
            'Fileobj': file,
        }
        return self.s3_client.download_fileobj(**params)

    def delete_object(self, key):
        params = {
            'Bucket': self.S3_BUCKET,
            'Key': key
        }
        return self.s3_client.delete_object(**params)

# Usage Example
# s3_service = S3Service()
# exists = s3_service.exists("example.txt")
# print(exists)
