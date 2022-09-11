import boto3
from moto import mock_s3
import unittest
import json
import os


env_name = 'DEV'  # os.environ['ENV']
region = 'us-east-1'  # PARAMS[env_name]['region']


class MyUnitTest(unittest.TestCase):

    BUCKET_NAME = "Stellar_Test_Buck"
    FILE_NAME = "sample_json.json"
    PATH = "./"
    PATH_ARCH = "./arch"
    PATH_NEW_SCHEMA = "./new_schema"
    PATH_DOWNLOAD = "./schema"
    FILE_LOCATION = f'{PATH}/{FILE_NAME}'
    S3_FILE_LOCATION_ARCH = f'{PATH_ARCH}/{FILE_NAME}'
    S3_FILE_LOCATION_NEW_SCHEMA = f'{PATH_NEW_SCHEMA}/{FILE_NAME}'
    FILE_LOCATION_DOWNLOAD = f'{PATH_DOWNLOAD}/{FILE_NAME}'
    print(os.getcwd())

    @mock_s3
    def test_archive_s3(self):
        from kstream.rollback import archive
        conn = boto3.resource('s3', region_name=region)
        conn.create_bucket(Bucket=self.BUCKET_NAME)
        print(self.FILE_LOCATION)
        f = open(self.FILE_LOCATION)
        resp = archive(record=json.load(f), record_name=self.S3_FILE_LOCATION_ARCH, BUCKET=self.BUCKET_NAME)
        respone = resp["ResponseMetadata"]["HTTPStatusCode"]
        assert respone == 200

    @mock_s3
    def test_send_record_to_s3(self):
        from kstream.rollback import CErrorTypes, send_record_to_s3
        conn = boto3.resource('s3', region_name=region)
        conn.create_bucket(Bucket=self.BUCKET_NAME)
        f = open(self.FILE_LOCATION)
        resp = send_record_to_s3(data=json.load(f), error=CErrorTypes.NEW_SCHEMA, file_name=self.S3_FILE_LOCATION_NEW_SCHEMA, BUCKET=self.BUCKET_NAME)
        respone = resp["ResponseMetadata"]["HTTPStatusCode"]
        assert respone == 200


if __name__ == '__main__':
    unittest.main()
