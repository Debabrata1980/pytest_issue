import json
import psycopg2
import boto3
import typer
import os.path as path

sm_client = boto3.client('secretsmanager', region_name='us-west-2')
RDS = "stellarbi/rds"
app = typer.Typer()


def db_conn(pg_credential):
    return psycopg2.connect(host=pg_credential.get('host'),
                            port=pg_credential.get('port'),
                            user=pg_credential.get('username'),
                            password=pg_credential.get('password'),
                            database=pg_credential.get('dbname'))


pg_credentials = json.loads(
    sm_client.get_secret_value(SecretId=RDS)['SecretString'])


def run_query(query: str):
    conn = db_conn(pg_credentials)
    cur = conn.cursor()
    try:
        cur.execute(query)
        resp = True
    except Exception:
        print("Query failed!")
        resp = None
    conn.commit()
    cur.close()
    conn.close()
    return resp


@app.command()
def help():
    pass


def parse_query(statements: list):
    countries = ['hpar', 'hpau', 'hpbr', 'hpcl', 'hpco', 'hphk', 'hpid2', 'hpin216', 'hpkr', 'hpmx', 'hpmy', 'hpnz', 'hppe', 'hpsg', 'hpth2']
    # countries = ['hpbr']
    for country in countries:
        print(f'Country: {country}')
        for s in statements:
            query = s.replace('{country}', country)
            run_query(query)
    return


@app.command()
def readquery(file_name: str):
    statements = []
    temp_statement = []
    if path.exists(f'{file_name}'):
        with open(file_name, 'r') as f1:
            for line in f1:
                line = line.strip()
                temp_statement.append(line)
                if ';' in line:
                    statements.append(' '.join(temp_statement))
                    temp_statement = []
        parse_query(statements)
        return
    print('File path incorrect!')
    return


if __name__ == "__main__":
    app()
