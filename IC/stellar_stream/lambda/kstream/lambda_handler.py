import base64
import json
import uuid
import sys
import os
from datetime import datetime
from pathlib import Path
from psycopg2 import sql
from c360.tokenization.tokens import Tokenizer

from decryption_handler import decrypt_record
from db_conn import db_conn
from schema_reader import db_schemas, db_tables
from rollback import CErrorTypes, send_record_to_s3, archive

from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from IC.stack_params import PARAMS
env_name = os.environ['ENV']
region = PARAMS[env_name]['region']
BUCKET = os.environ['S3_BUCKET']

lib_folder = Path(__file__).parent / "lib"
sys.path.insert(0, str(lib_folder))

metrics = Metrics(namespace="StellarStreaming")
today = datetime.now().strftime("%y-%m-%d")
T = Tokenizer()


def run_query(query, values):
    conn = db_conn()
    cur = conn.cursor()
    rows_affected = -1
    try:
        cur.execute(query, values)
        rows_affected = cur.rowcount
    except Exception as ex:
        print(f"Query: {query}")
        print(f"error: {ex}")

    conn.commit()
    cur.close()
    conn.close()
    return rows_affected


class ParseRecord:
    def __init__(self, record: bytes, rec_position: str):
        record_info = self._unpack_record(record)
        self.process(record_info, rec_position)
        archive(record_info['record'], record_info['file_location'], BUCKET)

    def _unpack_record(self, record):
        record_info = dict()
        record_info['record'] = base64.b64decode(record['kinesis']['data']).decode('utf-8')
        new_record = decrypt_record(record_info['record'])

        if new_record:
            record_info['record'] = new_record
            return record_info
        else:
            return False

    def _initialize_variables(self, rec_position, record_info):
        record_info['rows_affected'] = -1
        record_info['rec_position'] = rec_position
        record_info['record_status'] = 'Failure'
        record_info['schema'] = record_info['record']['schema']
        record_info['table'] = record_info['record']['table']
        record_info['primary_key'] = record_info['record']['Dict_PrimaryKeys'].keys()
        record_info['binlog_timestamp'] = record_info['record']['Timestamp']
        record_info['binlog_timestamp'] = datetime.utcfromtimestamp(record_info['binlog_timestamp']).strftime('%Y-%m-%d %H:%M:%S')
        record_info['binlog_read_timestamp'] = float(record_info['record']['ReadTime'])
        record_info['binlog_read_timestamp'] = datetime.utcfromtimestamp(record_info['binlog_read_timestamp']).strftime('%Y-%m-%d %H:%M:%S.%f')
        record_info['record_name'] = f"{record_info['binlog_timestamp']}_{uuid.uuid4().hex}".replace(':', '-').replace(' ', '-')
        record_info['file_location'] = f"{record_info['schema']}/{record_info['table']}/{today}/{record_info['record_name']}.json"

        return record_info

    def _record_type(self, record_info):
        if isinstance(record_info['record'], str):
            record_info['record'] = json.loads(record_info['record'])
        record_type = record_info['record']['type']
        if record_type == 'WriteRowsEvent':
            record_info['type'] = 'write'
            record_info['values'] = record_info['record']['row']['values']
        elif record_type == 'DeleteRowsEvent':
            record_info['type'] = 'delete'
            record_info['values'] = record_info['record']['row']['values']
        elif record_type == 'UpdateRowsEvent':
            record_info['type'] = 'update'
            record_info['values'] = record_info['record']['row']['after_values']
        else:
            record_info['type'] = None
            record_info['values'] = None

        if record_info['type'] is None:
            record_info['record_status'] = 'no_event_type_roll_back'
            print('Roll back - no event')
            send_record_to_s3(record_info['record'], CErrorTypes.SCHEMA_DEFINITION, record_info['file_location'], BUCKET)
            return False
        else:
            return record_info

    def _validate_data(self, record_info):
        if db_schemas.data.get(record_info['schema']) is None:
            send_record_to_s3(record_info['record'], CErrorTypes.SCHEMA_DEFINITION, record_info['file_location'], BUCKET)
            record_info['record_status'] = 'new_schema_roll_back'
            return False

        if db_tables.data.get(record_info['table']) is None:
            send_record_to_s3(record_info['record'], CErrorTypes.NEW_TABLE, record_info['file_location'], BUCKET)
            record_info['record_status'] = 'new_table_roll_back'
            return False

        for col in record_info['values'].keys():
            if db_tables.data[record_info['table']]['columns'].get(col) is None:
                send_record_to_s3(record_info['record'], CErrorTypes.NEW_COLUMNS, record_info['file_location'], BUCKET)
                record_info['record_status'] = 'new_column_roll_back'
                return False  # Breaking/Returning for any one new column

        return record_info

    def _generate_delete_query(self, record_info):
        fields = record_info['record']['Dict_PrimaryKeys'].keys()
        values = record_info['record']['Dict_PrimaryKeys'].values()

        query = sql.SQL('''DELETE FROM {schema}.{table} WHERE ({fields}) = ({values})''').format(
            schema=sql.Identifier(record_info['schema']),
            table=sql.Identifier(record_info['table']),
            fields=sql.SQL(", ").join(map(sql.Identifier, fields)),
            values=sql.SQL(', ').join(map(sql.Placeholder, fields)))

        record_info['rows_affected'] = run_query(query=query, values=dict(zip(fields, values)))
        if record_info['rows_affected'] == -1:
            record_info['record_status'] = 'query_roll_back'
            send_record_to_s3(record_info['record'], CErrorTypes.QUERY, record_info['file_location'])
            return False
        return True

    def _generate_upsert_query(self, record_info):
        fields = []
        values = []
        ex_list = ["excluded" for i in range(len(fields))]
        for k, v in record_info['values'].items():
            if v is None:
                continue

            if isinstance(v, str):
                v = v.replace("\\n", " ")
                v = v.replace("'", '"')
            fields.append(k)

            if isinstance(db_tables.data[record_info['table']]["columns"][k], str):
                v = T.tokens(
                    [v], data_class=db_tables.data[record_info['table']]["columns"][k])[0]
            values.append(v)

        fields.append('binlog_timestamp')
        values.append(record_info['binlog_timestamp'])
        fields.append('binlog_read_timestamp')
        values.append(record_info['binlog_read_timestamp'])

        query = sql.SQL("""insert into {schema}.{table} ({fields}) values ({values})
            ON CONFLICT ({primary_key})
            Do
            update set ({fields}) = ({ex_values})
            where "excluded"."binlog_read_timestamp" >=  {schema}.{table}.binlog_read_timestamp""").format(
            schema=sql.Identifier(record_info['schema']),
            table=sql.Identifier(record_info['table']),
            fields=sql.SQL(", ").join(map(sql.Identifier, fields)),
            values=sql.SQL(', ').join(map(sql.Placeholder, fields)),
            primary_key=sql.SQL(', ').join(map(sql.Identifier, record_info['primary_key'])),
            ex_values=sql.SQL(', ').join(map(sql.Identifier, ex_list, fields)))

        record_info['rows_affected'] = run_query(query=query, values=dict(zip(fields, values)))
        if record_info['rows_affected'] == -1:
            record_info['record_status'] = 'query_roll_back'
            send_record_to_s3(record_info['record'], CErrorTypes.QUERY, record_info['file_location'])
            return False
        return True

    def _generate_summary(self, record_info):
        pk_values = ','.join([str(i) for i in record_info['record']['Dict_PrimaryKeys'].values()])
        p_key = ','.join(record_info['primary_key'])
        fields = ['schema_name', 'table_name', 'pk', 'pk_values',
                  'binlog_timestamp', 'binlog_read_timestamp', 'file_name',
                  'error', 'status', 'event_type', 'rows_affected']
        values = (record_info['schema'], record_info['table'], p_key, pk_values,
                  record_info['binlog_timestamp'], record_info['binlog_read_timestamp'], record_info['record_name'],
                  '', record_info['record_status'], record_info['type'], record_info['rows_affected'])
        query = sql.SQL('''insert into {schema}.audit_info ({fields}) values ({values})''').format(
            schema=sql.Identifier(record_info['schema']),
            fields=sql.SQL(", ").join(map(sql.Identifier, fields)),
            values=sql.SQL(', ').join(map(sql.Placeholder, fields)))
        run_query(query=query, values=dict(zip(fields, values)))
        return True

    def _cloudwatch_logs(self, record_info):
        metrics.add_metadata(key='schema_' + record_info['rec_position'], value=record_info['schema'])
        metrics.add_metadata(key='table_' + record_info['rec_position'], value=record_info['table'])
        metrics.add_metadata(key='PK_' + record_info['rec_position'], value=str(record_info['primary_key']))
        metrics.add_metadata(key='file_name_' + record_info['rec_position'], value=record_info['record_name'])
        metrics.add_metadata(key='type_' + record_info['rec_position'], value=record_info['record']['type'])
        metrics.add_metadata(key='binlog_timestamp_' + record_info['rec_position'], value=record_info['binlog_timestamp'])
        metrics.add_metadata(key='binlog_read_timestamp_' + record_info['rec_position'], value=record_info['binlog_read_timestamp'])
        metrics.add_metadata(key='record_status_' + record_info['rec_position'], value=record_info['record_status'])
        metrics.add_metric(name='TableMapped_' + record_info['rec_position'], unit=MetricUnit.Count, value=1)

    def process(self, record_info, rec_position):
        # Encrypted records come from magento
        if record_info is False:
            return False

        record_info = self._record_type(record_info)
        if record_info is False:
            return False

        record_info = self._initialize_variables(rec_position, record_info)

        if not record_info['type']:
            record_info['record_status'] = 'no_event_type_roll_back'
            send_record_to_s3(record_info['record'], CErrorTypes.SCHEMA_DEFINITION, record_info['file_location'])
            return False

        if not self._validate_data(record_info) is False:
            return False

        if record_info['type'] == 'delete':
            record_info = self._generate_delete_query(record_info)
            if record_info is False:
                return False
            else:
                record_info['record_status'] = 'deleted' if record_info['rows_affected'] > 0 else 'no_action'
        else:
            record_info = self._generate_upsert_query(record_info)
            if record_info is False:
                return False
            else:
                record_info['record_status'] = 'inserted' if record_info['rows_affected'] > 0 else 'no_action'

        self._cloudwatch_logs(record_info)
        self._generate_summary(record_info)

        return


@metrics.log_metrics
def handler(event, context: LambdaContext):
    rec_position = 1
    for record in event.get('Records'):
        ParseRecord(record, str(rec_position))
        rec_position += 1
    return
