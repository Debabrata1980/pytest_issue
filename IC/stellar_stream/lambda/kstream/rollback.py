"""
This module handles rollback of records into S3
Rollback would be required in case of changes in schema or query errors
"""


import json
from enum import Enum
import boto3
# import os
from IC.stack_params import PARAMS

env_name = 'DEV'  # os.environ['ENV']
region = PARAMS[env_name]['region']
# s3 = boto3.resource('s3', region_name=region)
# BUCKET = os.environ['S3_BUCKET']
s3_client = boto3.client("s3")


class CErrorTypes(Enum):
    ENCRYPTION = 0
    NEW_SCHEMA = 1
    NEW_TABLE = 2
    NEW_COLUMNS = 3
    SCHEMA_DEFINITION = 4
    QUERY = 5


def _put_to_s3(data, file_name, BUCKET):
    s3 = boto3.resource('s3', region_name=region)
    s3object = s3.Object(BUCKET, file_name)
    resp = s3object.put(Body=(bytes(json.dumps(data).encode('UTF-8'))))
    return resp


def error_log(data_log, file_name, BUCKET):  # Used to Archive the logs
    location = 'log'
    s3_location = f'{env_name}/{location}/{file_name}'
    resp1 = _put_to_s3(data_log, s3_location, BUCKET)
    return resp1


def archive(record, record_name, BUCKET):  # Used to Archive the data
    location = 'archive'
    s3_location = f'{env_name}/{location}/{record_name}'
    resp2 = _put_to_s3(record, s3_location, BUCKET)
    return resp2


def send_record_to_s3(data, error: CErrorTypes, file_name, BUCKET):
    s3_folder = 'roll_back'
    if error == error.NEW_SCHEMA:
        location = f'{s3_folder}/new_schema'
    elif error == error.NEW_TABLE:
        location = f'{s3_folder}/new_table'
    elif error == error.NEW_COLUMNS:
        location = f'{s3_folder}/new_columns'
    elif error == error.SCHEMA_DEFINITION:
        location = f'{s3_folder}/unknown'
    elif error == error.QUERY:
        location = f'{s3_folder}/query'
    s3_location = f'{env_name}/{location}/{file_name}'
    resp3 = _put_to_s3(data, s3_location, BUCKET)
    return resp3
