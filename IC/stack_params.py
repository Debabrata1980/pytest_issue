import aws_cdk.aws_lambda as lmb
import aws_cdk.aws_iam as iam
from aws_cdk.core import Duration


def get_iam_policies(env_params):

    aws_region = env_params["region"]
    aws_account = env_params["account"]

    return [
        iam.PolicyStatement(sid="EnablePutLogs",
                            effect=iam.Effect.ALLOW,
                            actions=["logs:PutLogEvents"],
                            resources=[f"arn:aws:logs:*:{aws_account}:log-group:*:log-stream:*"]),
        iam.PolicyStatement(sid="EnableCreateLogs",
                            effect=iam.Effect.ALLOW,
                            actions=["logs:CreateLogStream",
                                     "logs:CreateLogGroup"],
                            resources=[f"arn:aws:logs:*:{aws_account}:log-group:*"]),
        iam.PolicyStatement(sid="EnableDynamodbTable",
                            effect=iam.Effect.ALLOW,
                            actions=["dynamodb:DescribeTable",
                                     "dynamodb:GetItem"],
                            resources=[f"arn:aws:dynamodb:{aws_region}:{aws_account}:table/sc_ww360_enc"]),
        iam.PolicyStatement(sid="S3Put", effect=iam.Effect.ALLOW, actions=["s3:PutObject", "s3:GetObject"],
                            resources=["arn:aws:s3:::s3-stellar-stream/*", "arn:aws:s3:::s3-stellar-stream"]),
        iam.PolicyStatement(sid="TokenizerService",
                            effect=iam.Effect.ALLOW,
                            actions=["lambda:InvokeFunction"],
                            resources=[f"arn:aws:lambda:{aws_region}:{aws_account}:function:TokenizerService"]),
        iam.PolicyStatement(sid="RDSSecrets",
                            effect=iam.Effect.ALLOW,
                            actions=["secretsmanager:GetSecretValue"],
                            resources=[f"arn:aws:secretsmanager:{aws_region}:{aws_account}:secret:{env_params['rds_secret_id']}"]),
        iam.PolicyStatement(sid="EnableNetworkCreation",
                            effect=iam.Effect.ALLOW,
                            actions=["ec2:CreateNetworkInterface",
                                     "ec2:DescribeNetworkInterfaces",
                                     "ec2:DeleteNetworkInterface"],
                            resources=["*"]),
        iam.PolicyStatement(sid="EnableStreamAccess",
                            effect=iam.Effect.ALLOW,
                            actions=["kinesis:DescribeStreamSummary",
                                     "kinesis:GetShardIterator",
                                     "kinesis:GetRecords"],
                            resources=[f"{env_params['kinesis_stream_arn']}"]),
        iam.PolicyStatement(sid="ListShards",
                            effect=iam.Effect.ALLOW,
                            actions=["kinesis:ListShards"],
                            resources=["*"]),
        iam.PolicyStatement(sid="SubscribeToShard",
                            effect=iam.Effect.ALLOW,
                            actions=["kinesis:SubscribeToShard"],
                            resources=[f"{env_params['kinesis_consumer_arn']}"])
    ]


# Define the production variables
PROD_REGION = "us-west-2"
PROD_VPC = "vpc-044e505a699b359c4"
PROD_SUBNET = ["subnet-0dff78583f067cef0"]
PROD_AZS = ["usw2-az2"]
PROD_ACCOUNT = "409599951855"
PROD_SECURITY_GROUP = "SG-stellar-stream-lambda"
PROD_PRIVATE_SUBNET_ROUTE_TABLE_IDS = ["rtb-089d1bcd6cab57540"]
PROD_RDS_SG_CIDR = "172.21.58.0/24"
PROD_STACK_NAME = "stellar-stream-lambda-prod"
PROD_SNS_TOPIC_ARN = f"arn:aws:sns:{PROD_REGION}:{PROD_ACCOUNT}:stellar-cw-dashboar-stack-KinesisAlarmTopic-1LWXVV357LT3P"
PROD_RDS_SECRET_ID = "stellarbi/rds_prod-9KN2oz"
PROD_STREAM_NAME = "magento-dev"
PROD_STREAM_CONSUMER_NAME = "StellarProd"
PROD_STREAM_CONSUMER_ID = "1656615130"
PROD_STREAM_ARN = f"arn:aws:kinesis:{PROD_REGION}:{PROD_ACCOUNT}:stream/{PROD_STREAM_NAME}"
PROD_STREAM_CONSUMER_ARN = f"{PROD_STREAM_ARN}/consumer/{PROD_STREAM_CONSUMER_NAME}:{PROD_STREAM_CONSUMER_ID}"

# Define the reprocess variables (for prod)
PROD_REPROCESS_STREAM_NAME = "reprocess-prod"

# Define the dev variables (for now, most will be the same as prod)
DEV_REGION = PROD_REGION
DEV_VPC = PROD_VPC
DEV_SUBNET = PROD_SUBNET
DEV_AZS = PROD_AZS
DEV_ACCOUNT = PROD_ACCOUNT
DEV_SECURITY_GROUP = "SG-stellar-stream-lambda-dev"
DEV_PRIVATE_SUBNET_ROUTE_TABLE_IDS = PROD_PRIVATE_SUBNET_ROUTE_TABLE_IDS
DEV_RDS_SG_CIDR = PROD_RDS_SG_CIDR
DEV_STACK_NAME = "stellar-stream-lambda"
DEV_SNS_TOPIC_ARN = f"arn:aws:sns:{DEV_REGION}:{DEV_ACCOUNT}:stellar-cw-dashboar-stack-KinesisAlarmTopic-1LWXVV357LT3P"
DEV_RDS_SECRET_ID = "stellarbi/rds-JdnZci"
DEV_STREAM_NAME = "magento-dev"
DEV_STREAM_CONSUMER_NAME = "StellarDev"
DEV_STREAM_CONSUMER_ID = "1656615125"
DEV_STREAM_ARN = f"arn:aws:kinesis:{DEV_REGION}:{DEV_ACCOUNT}:stream/{DEV_STREAM_NAME}"
DEV_STREAM_CONSUMER_ARN = f"{DEV_STREAM_ARN}/consumer/{DEV_STREAM_CONSUMER_NAME}:{DEV_STREAM_CONSUMER_ID}"

# Define the reprocess variables (for dev)
DEV_REPROCESS_STREAM_NAME = "reprocess-dev"

# The keys in the PARAMS dictionary are the git branches. The dev branch is deployed to the
# dev environment and master branch is deployed to the production environment.
PARAMS = {
    "dev": {
        "env_suffix": "dev",
        "stack_name": DEV_STACK_NAME,
        "account": DEV_ACCOUNT,
        "region": DEV_REGION,
        "vpc": DEV_VPC,
        "subnet": DEV_SUBNET,
        "azs": DEV_AZS,
        "sg": DEV_SECURITY_GROUP,
        "subnet_route_table_id": DEV_PRIVATE_SUBNET_ROUTE_TABLE_IDS,
        "rds_sg_cidr": DEV_RDS_SG_CIDR,
        "rds_secret_id": DEV_RDS_SECRET_ID,
        "sns_topic_arn": DEV_SNS_TOPIC_ARN,
        "stream_batch_size": 10,
        "stream_parallelization_factor": 10,
        "stream_retry_attempts": 5,
        "stream_bisect_batch_on_error": True,
        "stream_max_record_age": 60,
        "kinesis": "magento-dev",
        "kinesis_stream_arn": DEV_STREAM_ARN,
        "kinesis_consumer_arn": DEV_STREAM_CONSUMER_ARN,
        "reprocess_stream": DEV_REPROCESS_STREAM_NAME,
        "lambda": {
            "kstream": {
                "function_name": "stellar_stream_dev",
                "s3_reprocess_function_name": "stellar_stream_s3_reprocess_dev",
                "stream_reprocess_function_name": "stellar_stream_stream_reprocess_dev",
                "handler": "lambda_handler.handler",
                "s3_reprocess_handler": "s3_reprocess_handler.handler",
                "stream_reprocess_handler": "stream_reprocess_handler.handler",
                "memory_size": 300,
                "runtime": lmb.Runtime.PYTHON_3_8,
                "policy_name": "policy_lambda_stellar_stream_dev",
                "role_name": "role_lambda_stellar_stream_dev",
                "reprocess_policy_name": "policy_lambda_stellar_stream_reprocess_dev",
                "reprocess_role_name": "role_lambda_stellar_stream_reprocess_dev",
                "reprocess_consumer_name": "stellar_stream_consumer_reprocess_dev",
                "document_policy": None,
                "code_folder": "stellar_stream/lambda/kstream",
                "reprocess_code_folder": "stellar_stream/reprocess_lambda/kstream",
                "timeout": Duration.seconds(300),
                "environ": {"KINESIS": "magento-dev", "SECRETS_TABLE": "sc_ww360_enc", "RDS": "stellarbi/rds", "ENV": "DEV", "REPROCESS_KINESIS": DEV_REPROCESS_STREAM_NAME, "S3_BUCKET": "s3-stellar-stream"}
            },
        },
    },
    "master": {
        "env_suffix": "prod",
        "stack_name": PROD_STACK_NAME,
        "account": PROD_ACCOUNT,
        "region": PROD_REGION,
        "vpc": PROD_VPC,
        "subnet": PROD_SUBNET,
        "azs": PROD_AZS,
        "sg": PROD_SECURITY_GROUP,
        "subnet_route_table_id": PROD_PRIVATE_SUBNET_ROUTE_TABLE_IDS,
        "rds_sg_cidr": PROD_RDS_SG_CIDR,
        "rds_secret_id": PROD_RDS_SECRET_ID,
        "sns_topic_arn": PROD_SNS_TOPIC_ARN,
        "stream_batch_size": 10,
        "stream_parallelization_factor": 10,
        "stream_retry_attempts": 10,
        "stream_bisect_batch_on_error": False,
        "stream_max_record_age": 60 * 60 * 24,
        "kinesis": "magento-pro",
        "kinesis_stream_arn": PROD_STREAM_ARN,
        "kinesis_consumer_arn": PROD_STREAM_CONSUMER_ARN,
        "reprocess_stream": PROD_REPROCESS_STREAM_NAME,
        "lambda": {
            "kstream": {
                "function_name": "stellar_stream_pro",
                "s3_reprocess_function_name": "stellar_stream_s3_reprocess_prod",
                "stream_reprocess_function_name": "stellar_stream_stream_reprocess_prod",
                "handler": "lambda_handler.handler",
                "s3_reprocess_handler": "s3_reprocess_handler.handler",
                "stream_reprocess_handler": "stream_reprocess_handler.handler",
                "memory_size": 300,
                "runtime": lmb.Runtime.PYTHON_3_8,
                "policy_name": "policy_lambda_stellar_stream_pro",
                "role_name": "role_lambda_stellar_stream_pro",
                "reprocess_policy_name": "policy_lambda_stellar_stream_reprocess_prod",
                "reprocess_role_name": "role_lambda_stellar_stream_reprocess_prod",
                "reprocess_consumer_name": "stellar_stream_consumer_reprocess_prod",
                "document_policy": None,
                "code_folder": "stellar_stream/lambda/kstream",
                "reprocess_code_folder": "stellar_stream/reprocess_lambda/kstream",
                "timeout": Duration.seconds(300),
                "environ": {"KINESIS": "magento-pro", "SECRETS_TABLE": "sc_ww360_enc", "RDS": "stellarbi/rds_prod", "ENV": "PROD", "REPROCESS_KINESIS": PROD_REPROCESS_STREAM_NAME, "S3_BUCKET": "s3-stellar-stream"}},
        },
    }
}

# Finally, set the appropriate policy document for each environment
PARAMS["master"]["lambda"]["kstream"]["document_policy"] = get_iam_policies(PARAMS["master"])
PARAMS["dev"]["lambda"]["kstream"]["document_policy"] = get_iam_policies(PARAMS["dev"])
