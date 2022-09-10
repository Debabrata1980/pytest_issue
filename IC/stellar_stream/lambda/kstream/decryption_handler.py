"""Module handles decryption of rfernet encoded record"""

import os
import json
import boto3
from rfernet import Fernet as rFernet


dynamo_client = boto3.client('dynamodb', region_name='us-west-2')
SECRETS_TABLE = os.environ['SECRETS_TABLE']


def retrieve_rfernet_keys(dynamo_client, SECRETS_TABLE=SECRETS_TABLE):
    results = dynamo_client.get_item(
        TableName=SECRETS_TABLE,
        Key={
            'token': {'S': 'rfernet_magento'}
        }
    )
    return results['Item']['data']['S']


rfernet_keys = retrieve_rfernet_keys(dynamo_client, SECRETS_TABLE)
r_fernet = rFernet(rfernet_keys)


def decrypt_record(record: bytes):
    decrypted_record = None
    try:
        decrypted_record = json.loads(r_fernet.decrypt(record))
    except Exception:
        pass
    return decrypted_record
