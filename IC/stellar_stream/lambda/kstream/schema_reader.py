"""Module handles reading of schema in json format from S3 locations"""


import os
import json
import boto3
import os.path as path
from IC.stack_params import PARAMS

environment = str(os.environ['ENV'])
region = PARAMS[environment]['region']
s3 = boto3.resource('s3', region_name=region)
BUCKET = os.environ['S3_BUCKET']


class Schema:
    def __init__(self, file_name: str):
        self.file_name = file_name
        self.file_location = f'/tmp/{self.file_name}'
        self._download_file()
        self._read_data()

    def _download_file(self, BUCKET=BUCKET):
        file_name = f'schema/{environment}/{self.file_name}'
        print(f'Downloading file: {file_name}')
        s3.Bucket(BUCKET).download_file(file_name, self.file_location)
        return

    def _read_data(self):
        file_name = path.join(path.dirname(path.abspath(__file__)), self.file_location)
        with open(file_name, 'r') as myfile:
            self.data = json.loads(myfile.read())

    def _write_to_data(self, BUCKET=BUCKET):
        file_name = f'schema/{environment}/{self.file_name}'
        print(f'Writing to file: {file_name}')
        s3object = s3.Object(BUCKET, file_name)
        s3object.put(
            Body=(bytes(json.dumps(self.data).encode('UTF-8')))
        )


db_schemas = Schema('db_schemas.json')
db_tables = Schema('db_tables.json')
