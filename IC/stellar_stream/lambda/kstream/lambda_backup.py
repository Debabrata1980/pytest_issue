import base64
import json
import boto3
import uuid
import re
import sys
import datetime
from enum import Enum
from pathlib import Path
from c360.tokenization.tokens import Tokenizer

from decryption_handler import decrypt_record
from db_conn import db_conn
from schema_reader import db_schemas, db_tables

from aws_lambda_powertools import Metrics
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext

lib_folder = Path(__file__).parent / "lib"
sys.path.insert(0, str(lib_folder))


s3 = boto3.resource('s3', region_name='us-west-2')

BUCKET = "s3-stellar-stream"
today = datetime.now().strftime("%y-%m-%d")
T = Tokenizer()


class CErrorTypes(Enum):
    ENCRYPTION = 0
    NEW_SCHEMA = 1
    NEW_TABLE = 2
    NEW_COLUMNS = 3
    SCHEMA_DEFINITION = 4
    QUERY = 5


metrics = Metrics(namespace="StellarStreaming")


def test_run_query(query: str):
    conn = db_conn()
    cur = conn.cursor()
    cur.execute(query)
    raw_data = cur.fetchall()
    conn.commit()
    cur.close()
    conn.close()
    return raw_data


event_id = f'{today}_{uuid.uuid4().hex}'


class ParseRecord:
    def __init__(self, record: bytes, event: bytes, rec_position: str):
        self.event = event
        self.record = base64.b64decode(
            record['kinesis']['data']).decode('utf-8')
        self.new_columns = []
        self.error_logger = {}
        self.record_name = f'{today}_{uuid.uuid4().hex}'
        self.rec_position = rec_position
        self.record_status = 'Failure'
        self.process()

    def _put_to_s3(self, data, file_name):
        s3object = s3.Object(BUCKET, file_name)
        s3object.put(Body=(bytes(json.dumps(data).encode('UTF-8'))))

    def _error_log(self, logs_location='logs'):  # Used to Archive the logs
        # logs_location = '10thMay_new_columns_error_2'
        file_name = f'{logs_location}/{self.schema}/{self.table}/{self.record_name}.json'
        self._put_to_s3(self.error_logger, file_name)
        return

    def _archive(self):  # Used to Archive the data
        location = 'backup'
        file_name = f'{location}/{self.table}/{self.schema}/{self.record_name}.json'
        self._put_to_s3(self.record, file_name)
        return

    def _send_record_to_s3(self, error: CErrorTypes):
        if error == error.NEW_SCHEMA:
            location = 'error/new_schema'
        elif error == error.NEW_TABLE:
            location = 'error/new_table'
        elif error == error.NEW_COLUMNS:
            location = 'error/new_columns'
        elif error == error.SCHEMA_DEFINITION:
            location = 'error/unknown'
        elif error == error.QUERY:
            location = 'error/query'

        file_name = f'{location}/{self.table}/{self.schema}/{self.record_name}.json'
        self._put_to_s3(self.record, file_name)
        metrics.add_metadata(key='error_' + self.rec_position, value=location)
        return

    def _record_type(self):
        if isinstance(self.record, str):
            self.record = json.loads(self.record)
        record_type = self.record['type']
        if record_type == 'WriteRowsEvent':
            self.type = 'write'
            self.values = self.record['row']['values']
        elif record_type == 'DeleteRowsEvent':
            self.type = 'delete'
            self.values = self.record['row']['values']
        elif record_type == 'UpdateRowsEvent':
            self.type = 'update'
            self.values = self.record['row']['after_values']
        self.schema = self.record['schema']
        self.table = self.record['table']
        self.primary_key = db_tables.data[self.table]['primary_key']
        self.kinesis_timestamp = self.record['Timestamp']
        self.kinesis_timestamp = datetime.utcfromtimestamp(self.kinesis_timestamp).strftime('%Y-%m-%d %H:%M:%S')

        self.error_logger['_record_type'] = {'schema': self.schema, 'table': self.table, 'function': '_record_type', 'data': '', 'query': '', 'file_name': self.record_name, 'event_id': event_id}
        self._error_log()
        return

    def _identify_pii(self, col):
        # Email case
        value = self.values[col]
        if len(re.findall("([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\\.[a-zA-Z0-9-.]+)", value)) > 0:
            db_tables.data[self.table]['columns'].update({col: 'email'})
        return

    # def _dtype(self, col):
    #     value = self.values[col]
    #     if not value:
    #         return 'NULL'
    #     if str(value) in ['NULL', '0000-00-00 00:00:00', 'None']:
    #         return 'NULL'
    #     if isinstance(value, str):
    #         return 'str'
    #     value = str(value)
    #     try:
    #         dtype = type(literal_eval(value))
    #     except (ValueError, SyntaxError):
    #         dtype = str
    #     if dtype == float:
    #         return 'float'
    #     elif dtype == int:
    #         return 'int'
    #     elif dtype == str:
    #         return 'str'
    #     elif dtype == dict:
    #         return 'str'
    #     return 'NULL'

    def _validate_data(self):
        if not db_schemas.data.get(self.schema):
            self._send_record_to_s3(CErrorTypes.NEW_SCHEMA)
            self.error_logger['_validate_data'] = {'schema': self.schema, 'table': self.table, 'function': '_validate_data', 'data': 'New Schema', 'query': '', 'file_name': self.record_name, 'event_id': event_id}
            self._error_log()
            return

        if not db_tables.data.get(self.table):
            self._send_record_to_s3(CErrorTypes.NEW_TABLE)
            self.error_logger['_validate_data'] = {'schema': self.schema, 'table': self.table, 'function': '_validate_data', 'data': 'New Schema', 'query': '', 'file_name': self.record_name, 'event_id': event_id}
            self._error_log()
            return
        # temp_values={}
        for col in self.values.keys():
            # temp_values[col]=db_tables.data[self.table]['columns'].get(col) #Used for debudding [Lambda with new columns are passing this check/fucntion and no roll back is performed]
            # temp_values[col+'_Bool']=not db_tables.data[self.table]['columns'].get(col)  #Used for debudding [Lambda with new columns are passing this check/fucntion and no roll back is performed]
            if not db_tables.data[self.table]['columns'].get(col):
                self.error_logger['_validate_data'] = {'schema': self.schema, 'table': self.table, 'function': '_validate_data', 'data': 'New Schema', 'query': '', 'file_name': self.record_name, 'event_id': event_id}
                self._error_log()
                self._send_record_to_s3(CErrorTypes.NEW_COLUMNS)
                # dtype = self._dtype(col)
                # if dtype == 'NULL':
                #     continue
                # self.new_columns.append((col, dtype))
                return  # Breaking/Returning for any one new column

        self.error_logger['_validate_data'] = {'schema': self.schema, 'table': self.table, 'function': '_validate_data', 'data': 'No Roll Back', 'query': '', 'file_name': self.record_name, 'event_id': event_id}
        self._error_log()
        return True

    def run_query(self, query: str, event: bytes):
        conn = db_conn()
        cur = conn.cursor()
        try:
            cur.execute(query)
            resp = True
        except Exception as ex:
            print(f"Query: {query}")
            metrics.add_metadata(key='query-error_' + self.rec_position, value=f"query: {query} record: {event}")
            metrics.add_metadata(key='exception_summary_' + self.rec_position, value=f"exception':{ex} exception_type: {type(ex).__name__} arguments: {ex.args}")
            resp = None
        conn.commit()
        cur.close()
        conn.close()
        return resp

    # def _modify_postgres_build_query(self, dtype: str):
    #     ctype = None
    #     if dtype == 'int':
    #         ctype = 'integer'
    #     elif dtype == 'float':
    #         ctype = 'numeric(20,4)'
    #     elif dtype == 'str':
    #         ctype = 'character varying(255)'
    #     return ctype

    # def _modify_postgres(self):
    #     dquery = ''
    #     for cols in self.new_columns:
    #         col = cols[0]
    #         if cols[1] == 'NULL':
    #             del self.values[col]
    #             continue
    #         dtype = self._modify_postgres_build_query(cols[1])
    #         dquery += f' ADD COLUMN {col} {dtype} ,'
    #     dquery = dquery[:-1]
    #     for country in db_schemas.data:
    #         query = f"ALTER Table main.{country}.{self.table} {dquery}"
    #         self.run_query(query, self.event)
    #     return

    # def _modify_dtable(self):
    #     for cols in self.new_columns:
    #         if not self.values.get(cols[0]):
    #             continue
    #         col = cols[0]
    #         value = self.values[cols[0]]
    #         dtype = cols[1]
    #         db_tables.data[self.table]['columns'].update({col: True})
    #         # Pii data
    #         if dtype == 'str':
    #             self._identify_pii(col)
    #     db_tables._write_to_data()
    #     return

    # def _modify_schema(self):
    #     self._modify_postgres()
    #     self._modify_dtable()

    def _generate_delete_query(self):
        new_filter = ''
        for col in self.primary_key:
            if isinstance(self.values[col], int):
                primary_key_value = f"{col} = {self.values[col]} AND "
            else:
                primary_key_value = f"{col} = '{self.values[col]}' AND "
            new_filter += primary_key_value
        new_filter = new_filter[:-5]
        query = f"DELETE FROM main.{self.schema}.{self.table} WHERE {new_filter}"
        self.error_logger['_generate_delete_query'] = {'schema': self.schema, 'table': self.table, 'function': '_generate_delete_query', 'data': new_filter, 'query': query, 'file_name': self.record_name, 'event_id': event_id}
        self._error_log()
        query = self.run_query(query, self.event)
        if not query:
            self._send_record_to_s3(CErrorTypes.QUERY)
            return
        return True

    # def _validate_insert(self, value):
    #     if str(value) in ['NULL', '0000-00-00 00:00:00', 'None']:
    #         return
    #     return True

    # def _check_record(self):  #Temporary Fucntion to check if a delete was successfully performed or not
    #     new_filter = ''
    #     for col in self.primary_key:
    #         if isinstance(self.values[col], int):
    #             primary_key_value = f"{col} = {self.values[col]} AND "
    #         else:
    #             primary_key_value = f"{col} = '{self.values[col]}' AND "
    #         new_filter += primary_key_value
    #     new_filter = new_filter[:-5]
    #     query = f"SELECT * FROM main.{self.schema}.{self.table} WHERE {new_filter}"
    #     query_results = test_run_query(query)
    #     #record_status= 'Record was found even after delete' if len(query_results)>0 else 'All OK! Record was not found after delete'
    #     self.error_logger['_check_record']={'schema':self.schema,'table':self.table,'function':'_check_record','data':query_results,'query':query,'record_status':self.record_status,'file_name':self.record_name,'event_id':event_id}
    #     self._error_log()

    #     metrics.add_metadata(key='Record_status_'+self.rec_position, value=self.record_status)
    #     return True

    def _handle_int_and_str(self, value_to_handle):
        if isinstance(value_to_handle, int):
            value_to_handle = f"{value_to_handle}"
        else:
            value_to_handle = f"'{value_to_handle}'"
        return value_to_handle

    def _get_key_values(self):
        new_filter = ''
        for col in self.primary_key:
            if isinstance(self.values[col], int):
                primary_key_value = f"{col} = {self.values[col]} AND "
            else:
                primary_key_value = f"{col} = '{self.values[col]}' AND "
            new_filter += primary_key_value
        new_filter = new_filter[:-5]
        return new_filter

    def _generate_upsert_query(self):
        fields = []
        values = []
        for k, v in self.values.items():
            try:
                if v is None:
                    continue
                if isinstance(v, str):
                    v = v.replace("\\n", " ")
                    v = v.replace("'", '"')
                fields.append(k)
                if isinstance(db_tables.data[self.table]["columns"][k], str):
                    v = T.tokens(
                        [v], data_class=db_tables.data[self.table]["columns"][k])[0]
                values.append(v)
            except Exception as e:
                self.error_logger['_generate_insert_query'] = {'schema': self.schema, 'table': self.table, 'function': '_generate_insert_query', 'data': str(values), 'Exception': str(e), 'file_name': self.record_name, 'event_id': event_id}
                self._error_log('Error_fix_10thMay')
                return False

        fields.append('kinesis_timestamp')
        values.append(self.kinesis_timestamp)

        key_value_filter = self._get_key_values()

        update_fields = ', '.join([f"{i}={self._handle_int_and_str(j)}" for i, j in zip(fields, values)])
        values = tuple(values)
        fields = f"{fields}".replace("[", "").replace("]", "").replace("'", "")

        query = f'''insert into main.{self.schema}.{self.table} ({fields}) values {values}
                    ON CONFLICT {'('+','.join(self.primary_key)+')'}
                    Do
                    update set {update_fields}
                    where '{self.kinesis_timestamp}' > (select kinesis_timestamp from main.{self.schema}.{self.table} where {key_value_filter})'''

        self.error_logger['_generate_upsert_query'] = {'schema': self.schema, 'table': self.table, 'function': '_generate_insert_query', 'data': values, 'query': query, 'file_name': self.record_name, 'event_id': event_id}
        self._error_log()
        query = self.run_query(query, self.event)
        if not query:
            self._send_record_to_s3(CErrorTypes.QUERY)
            return
        return True

    # def _generate_insert_query(self):
    #     fields = []
    #     values = []

    #     for k, v in self.values.items():
    #         try:
    #             if  v is None:
    #                 continue
    #             if isinstance(v, str):
    #                 v = v.replace("\\n", " ")
    #                 v = v.replace("'", '"')
    #             fields.append(k)
    #             if isinstance(db_tables.data[self.table]["columns"][k], str):
    #                 v = T.tokens(
    #                     [v], data_class=db_tables.data[self.table]["columns"][k])[0]
    #             values.append(v)
    #         except Exception as e:
    #             self.error_logger['_generate_insert_query']={'schema':self.schema,'table':self.table,'function':'_generate_insert_query','data':str(values),'Exception':str(e),'file_name':self.record_name,'event_id':event_id}
    #             self._error_log('Error_fix_10thMay')
    #             return False
    #     fields.append('kinesis_timestamp')
    #     values.append(self.kinesis_timestamp)
    #     values = tuple(values)
    #     fields = f"{fields}".replace(
    #         "[", "").replace("]", "").replace("'", "")
    #     query = f'insert into main.{self.schema}.{self.table} ({fields}) values {values}'

    #     self.error_logger['_generate_insert_query']={'schema':self.schema,'table':self.table,'function':'_generate_insert_query','data':values,'query':query,'file_name':self.record_name,'event_id':event_id}
    #     self._error_log()
    #     query = self.run_query(query, self.event)
    #     if not query:
    #         self._send_record_to_s3(CErrorTypes.QUERY)
    #         return
    #     return True

    def _generate_summary(self):
        pk_values = ','.join([str(i) for i in self.record['Dict_PrimaryKeys'].values()])
        p_key = ','.join(self.primary_key)
        query = f'''insert into main.{self.schema}.audit_info ("schema","table",pk,pk_values,kinesis_timestamp,file_name,error,status,event_type)
        values ('{self.schema}','{self.table}','{p_key}','{pk_values}','{self.kinesis_timestamp}','{self.record_name}','','{self.record_status}','{self.type}')'''
        query = self.run_query(query, self.event)
        return

    def process(self):
        # Encrypted records come from magento
        new_record = decrypt_record(self.record)
        if new_record:
            self.record = new_record
        self._record_type()
        self._archive()

        metrics.add_metadata(key='schema_' + self.rec_position, value=self.schema)
        metrics.add_metadata(key='table_' + self.rec_position, value=self.table)
        metrics.add_metadata(key='PK_' + self.rec_position, value=str(self.primary_key))
        metrics.add_metadata(key='file_name_' + self.rec_position, value=self.record_name)
        metrics.add_metadata(key='type_' + self.rec_position, value=new_record['type'])
        metrics.add_metadata(key='Kinesis_timestamp_' + self.rec_position, value=self.kinesis_timestamp)
        metrics.add_metadata(key='record_status_' + self.rec_position, value=self.record_status)

        try:
            self.error_logger['Process'] = {'schema': new_record['schema'], 'table': new_record['table'], 'function': 'Process', 'data': new_record['row']['values'], 'query': '', 'file_name': self.record_name, 'event_id': event_id}
        except KeyError:
            self.error_logger['Process'] = {'schema': new_record['schema'], 'table': new_record['table'], 'function': 'Process', 'data': new_record['row']['after_values'], 'query': '', 'file_name': self.record_name, 'event_id': event_id}
        self._error_log()

        if not self.type:
            self._generate_summary()
            self._send_record_to_s3(CErrorTypes.SCHEMA_DEFINITION)
            return

        if not self._validate_data():
            self._generate_summary()
            return
        # Process new columns
        # if len(self.new_columns) > 0:
        #     self._modify_schema()

        # if not self._generate_delete_query():
        #     return

        if self.type == 'delete':
            if not self._generate_delete_query():
                self._generate_summary()
                return
            self.record_status = 'Success'
            metrics.add_metadata(key='record_status_' + self.rec_position, value=self.record_status)
            self._generate_summary()
            return

        # self._check_record()

        # if not self._generate_insert_query():
        #     return

        if not self._generate_upsert_query():
            return

        self.record_status = 'Success'
        self._generate_summary()

        # self.error_logger['Process_end']={'schema':new_record['schema'],'table':new_record['table'],'function':'Process_end','data':new_record['row']['values'],'query':'','file_name':self.record_name,'event_id':event_id}
        self.error_logger['Process_end'] = {'schema': self.schema, 'table': self.table, 'function': 'Process_end2', 'data': '', 'query': '', 'file_name': self.record_name, 'event_id': event_id}
        self._error_log()

        metrics.add_metadata(key='record_status_' + self.rec_position, value='Success')
        metrics.add_metric(name='TableMapped_' + self.rec_position, unit=MetricUnit.Count, value=1)
        return


@metrics.log_metrics
def handler(event, context: LambdaContext):
    rec_position = 1
    for record in event.get('Records'):
        ParseRecord(record, event, str(rec_position))
        rec_position += 1
    return
