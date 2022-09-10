import boto3
import typer
import json
import shutil
import random
import os
from ast import literal_eval
import os.path as path

app = typer.Typer()
s3 = boto3.resource('s3', region_name='us-west-2')
kinesis = boto3.client('kinesis', region_name='us-west-2')
BUCKET = "s3-stellar-stream"


class Schema:
    def __init__(self, file_name: str):
        self.file_name = file_name
        self.file_location = f'/tmp/{self.file_name}'
        self._download_file()
        self._read_data()

    def _download_file(self):
        s3.Bucket(BUCKET).download_file(
            f'schema/{self.file_name}', self.file_location)
        return

    def _read_data(self):
        file_name = path.join(path.dirname(
            path.abspath(__file__)), self.file_location)
        with open(file_name, 'r') as myfile:
            self.data = json.loads(myfile.read())

    def _write_to_data(self):
        file_name = f'schema/{self.file_name}'
        s3object = s3.Object(BUCKET, file_name)
        s3object.put(
            Body=(bytes(json.dumps(self.data).encode('UTF-8')))
        )


db_tables = Schema('db_tables.json')


def read_s3_files(bucket_name: str, folder: str, retrieve: int = 1):
    bucket = s3.Bucket(bucket_name)
    files = []
    counter = 1
    for obj in bucket.objects.filter(Prefix=folder):
        if counter > retrieve:
            break
        files.append(obj)
        counter += 1
    return files


@app.command()
def help():
    pass


def read_headers(file_name: str):
    if not os.path.exists(file_name):
        print('File dosent exist!')
        return
    with open(file_name, 'r', encoding='utf-8', errors="ignore") as f1:
        for line in f1:
            return line.strip().split('<<<')


def read_file(file_name: str, start_at_row: int, end_at_row: int):
    data = []
    if end_at_row < 1:
        return
    with open(file_name, 'rb') as f1:
        next(f1)
        c = 1
        for line in f1:
            c += 1
            if start_at_row > c:
                continue
            line = line.decode('utf-8', 'ignore').strip().split('<<<')
            data.append(line)
            if c > end_at_row:
                break
    return data


def validate_columns(columns: list, table_name: str):
    missing_columns = []
    for col in columns:
        if not db_tables.data[table_name]['columns'].get(col):
            missing_columns.append(col)
    if len(missing_columns) > 0:
        print('Columns missing in Postgres')
        print(missing_columns)
        return
    return True


def funcdtype(value):
    if not value:
        return 'NULL'
    if str(value) in ['NULL', '0000-00-00 00:00:00', 'None']:
        return 'NULL'
    value = str(value)
    try:
        dtype = type(literal_eval(value))
    except (ValueError, SyntaxError):
        dtype = str
    if dtype == float:
        return 'float'
    elif dtype == int:
        return 'int'
    elif dtype == str:
        return 'str'
    elif dtype == dict:
        return 'str'
    return 'NULL'


def parse_row(row: list, headers: list, schema_name: str, table_name: str):
    new_row = {'schema': schema_name, 'table': table_name,
               'type': 'WriteRowsEvent', 'row': {'values': {}}}
    for h, v in zip(headers, row):
        dtype = funcdtype(v)
        if dtype == 'NULL':
            continue
        if dtype == 'float':
            v = float(v)
        elif dtype == 'int':
            v = int(v)
        elif dtype == 'str':
            v = str(v)
            v = v.replace('\\n', ' ')
        elif dtype == 'dict':
            v = str(v)
        new_row['row']['values'].update({h: v})
    return new_row


def parse_data(stream_name: str, data: list, headers: list, schema_name: str, table_name: str, ):
    unique = set()
    for c, row in enumerate(data):
        record = parse_row(row, headers, schema_name, table_name)
        n = f'partition_{random.randint(0, 10)}'

        try:
            kinesis.put_record(
                StreamName=stream_name,
                Data=json.dumps(record),
                PartitionKey=n,
            )
        except Exception:
            print(f'Failed at row: {c}')
            print(record)
            break

    print(len(unique))
    return


@app.command()
def dummydata(stream_name: str, schema_name: str, table_name: str, data: str):
    new_row = {'schema': schema_name, 'table': table_name,
               'type': 'WriteRowsEvent', 'row': {'values': {}}}
    data = data.replace("'", '"')
    data = json.loads(data)
    new_row['row']['values'].update(data)
    n = f'partition_{random.randint(0, 10)}'
    try:
        kinesis.put_record(
            StreamName=stream_name,
            Data=json.dumps(new_row),
            PartitionKey=n,
        )
    except Exception:
        print(f'Failed {new_row}')
    return


@app.command()
def datadump(stream_name: str, file_name: str, schema_name: str, table_name: str, start_at_row: int, end_at_row: int):
    headers = read_headers(file_name)
    num_of_headers = len(headers)
    print(f"Number of headers: {num_of_headers}")
    if not validate_columns(headers, table_name):
        return
    print("---Parsing file---")
    data = read_file(file_name, start_at_row, end_at_row)
    if not data:
        return
    print(f"Number of rows: {len(data)}")
    parse_data(stream_name, data, headers, schema_name, table_name)


@app.command()
def comparefile(table_name: str, schema_name: str, folder_name: str, file_name: str, bucket_name: str = 's3-stellar-stream'):
    file_name = f'{folder_name}/{table_name}/{schema_name}/{file_name}'
    file = s3.Object(bucket_name, file_name).get()
    record = json.loads(file['Body'].read().decode('utf-8'))
    if record['type'] == 'DeleteRowsEvent':
        record = record['row']['values']
    elif record['type'] == 'WriteRowsEvent':
        record = record['row']['values']
    elif record['type'] == 'UpdateRowsEvent':
        record = record['row']['after_values']
    extra_fields = []
    for k, v in record.items():
        if k not in db_tables.data[table_name]['columns']:
            extra_fields.append((k, v))
    print(extra_fields)


@app.command()
def updatelambda(env: str, bucket_name: str = 's3-stellar-stream'):
    function_name = f'stellar_stream_{env}'
    lambda_client = boto3.client('lambda', region_name='us-west-2')
    lambda_location = f'../../../IC/stellar_stream/lambda/kstream/{env}'
    # Zip function
    shutil.make_archive('lambda_code', 'zip',
                        root_dir=lambda_location, verbose=True)
    # Check file size
    lambda_code_size = os.path.getsize('lambda_code.zip')
    if not lambda_code_size > 10000000:
        print('---Error: Check lambda zip file---')
        return
    # Upload zip to S3
    s3.Bucket(bucket_name).upload_file(
        './lambda_code.zip', f'lambda/{env}/lambda_code.zip')
    # Upload function
    lambda_client.update_function_code(
        FunctionName=function_name,
        S3Bucket=bucket_name,
        S3Key=f'lambda/{env}/lambda_code.zip')

    return


def _recordtype(record: dict):
    return record['row']['after_values'] if record['type'] == 'UpdateRowsEvent' else record['row']['values']


@app.command()
def reprocess(folder_name: str, retrieve: int, bucket_name: str = 's3-stellar-stream', stream_name: str = 'magento-pro'):
    folder = f'error/{folder_name}'
    list_of_files = read_s3_files(bucket_name, folder, retrieve)
    if len(list_of_files) > 0:
        for i in list_of_files:
            file = s3.Object(bucket_name, i.key).get()
            record = file['Body'].read()
            record = record.replace(b'\\n', b' ')
            try:
                record = json.loads(record.decode('utf-8', 'ignore'))
            except Exception:
                print("Error with record")
                return
            schema_name = record['schema']
            table_name = record['table']
            record = _recordtype(record)
            headers = list(record.keys())
            row = list(record.values())
            row = parse_row(row, headers, schema_name, table_name)
            kinesis.put_record(
                StreamName=stream_name,
                Data=json.dumps(row),
                PartitionKey='reproces',
            )
            # print(row)
            # print(response)
            s3.Object(bucket_name, i.key).delete()
    return


if __name__ == "__main__":
    app()
