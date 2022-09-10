"""Module handles establishment of connection to Postgres database"""


import json
import psycopg2
import boto3
import os
from IC.stack_params import PARAMS

env_name = os.environ['ENV']
region = PARAMS[env_name]['region']
sm_client = boto3.client('secretsmanager', region_name=region)
rds_name = os.environ['RDS']


def db_conn(rds_name=rds_name):
    pg_credential = json.loads(sm_client.get_secret_value(SecretId=rds_name)['SecretString'])
    return psycopg2.connect(host=pg_credential.get('host'),
                            port=pg_credential.get('port'),
                            user=pg_credential.get('username'),
                            password=pg_credential.get('password'),
                            database=pg_credential.get('dbname'))
