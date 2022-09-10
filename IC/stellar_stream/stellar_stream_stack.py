from aws_cdk import core
import aws_cdk.aws_lambda_event_sources as event_sources
import aws_cdk.aws_kinesis as kinesis
import aws_cdk.aws_lambda as lmb
import aws_cdk.aws_iam as iam
import aws_cdk.aws_ec2 as ec2
import aws_cdk.aws_sns as sns
from aws_cdk.aws_lambda_event_sources import SnsEventSource
from teams_notifier_construct import TeamsNotifier


class StellarStreamStack(core.Stack):

    def __init__(self, scope: core.Construct, construct_id: str, params: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Setup some variables for string formatting
        aws_account = params["account"]
        aws_region = params["region"]

        # Define VPC
        vpc = ec2.Vpc.from_vpc_attributes(self,
                                          "VPC",
                                          vpc_id=params["vpc"],
                                          availability_zones=params["azs"],
                                          private_subnet_ids=params["subnet"],
                                          private_subnet_route_table_ids=params["subnet_route_table_id"])

        # Define SG
        sg = ec2.SecurityGroup(self, "SG", vpc=vpc, allow_all_outbound=True, security_group_name=params["sg"])
        sg.add_ingress_rule(ec2.Peer.ipv4(params["rds_sg_cidr"]), ec2.Port.tcp(5432), "allow Postgres RDS from VPC")
        # The code that defines your stack goes here
        kinesis_stream = kinesis.Stream.from_stream_arn(
            self, "KinesisStream_" + params["env_suffix"],
            params["kinesis_consumer_arn"]
        )

        sns.Topic.from_topic_arn(self,
                                 id='error_sns_topic',
                                 topic_arn=params["sns_topic_arn"])

        kinesis_event_source = event_sources.KinesisEventSource(
            stream=kinesis_stream,
            starting_position=lmb.StartingPosition.TRIM_HORIZON,
            batch_size=params["stream_batch_size"],
            parallelization_factor=params["stream_parallelization_factor"],
            retry_attempts=params["stream_retry_attempts"],
            bisect_batch_on_error=params["stream_bisect_batch_on_error"],
            max_record_age=core.Duration.seconds(params["stream_max_record_age"])
        )

        # Lambda function
        role1 = iam.Role(
            self, "Role1", role_name=params["lambda"]["kstream"]["role_name"],
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"))

        iam.Policy(
            self, "Policy1", policy_name=params["lambda"]["kstream"]["policy_name"],
            document=iam.PolicyDocument(statements=params["lambda"]["kstream"]["document_policy"]), force=True, roles=[role1])

        powertools_layer = lmb.LayerVersion.from_layer_version_arn(
            self,
            id="lambda-powertools",
            layer_version_arn="arn:aws:lambda:us-west-2:017000801446:layer:AWSLambdaPowertoolsPython:17"
        )

        c360_tokenization_layer = lmb.LayerVersion.from_layer_version_arn(
            self,
            id="c360-tokenization",
            layer_version_arn=f"arn:aws:lambda:{aws_region}:{aws_account}:layer:c360-tokenization:2"
        )

        psycopg2_layer = lmb.LayerVersion.from_layer_version_arn(
            self,
            id="psycopg2",
            layer_version_arn=f"arn:aws:lambda:{aws_region}:{aws_account}:layer:psycopg2:2"
        )

        rfernet_layer = lmb.LayerVersion.from_layer_version_arn(
            self,
            id="rfernet",
            layer_version_arn=f"arn:aws:lambda:{aws_region}:{aws_account}:layer:rfernet:1"
        )

        func1 = lmb.Function(self, "func1" + params["env_suffix"],
                             runtime=params["lambda"]["kstream"]["runtime"],
                             layers=[powertools_layer, c360_tokenization_layer, psycopg2_layer, rfernet_layer],
                             function_name=params["lambda"]["kstream"]["function_name"],
                             handler=params["lambda"]["kstream"]["handler"],
                             memory_size=params["lambda"]["kstream"]["memory_size"],
                             role=role1,
                             timeout=params["lambda"]["kstream"]["timeout"],
                             environment=params["lambda"]["kstream"]["environ"],
                             vpc=vpc,
                             security_group=sg,
                             code=lmb.Code.from_asset(
                                   params["lambda"]["kstream"]["code_folder"])
                             )
        func1.add_event_source(kinesis_event_source)

        cw_alarm_notification = TeamsNotifier(self, "CwAlarmNotification")

        database_topic_arn = f'arn:aws:sns:{aws_region}:{aws_account}:stellar-cw-dashboar-stack-DatabaseAlarmTopic-1WM83SYXHEMNX'

        database_topic = sns.Topic.from_topic_arn(self,
                                                  'database_topic',
                                                  database_topic_arn)
        cw_alarm_notification._teams_notifier.add_event_source(SnsEventSource(database_topic))

        kinesis_topic_arn = f'arn:aws:sns:{aws_region}:{aws_account}:stellar-cw-dashboar-stack-KinesisAlarmTopic-1LWXVV357LT3P'

        kinesis_topic = sns.Topic.from_topic_arn(self,
                                                 'kinesis_topic',
                                                 kinesis_topic_arn)
        cw_alarm_notification._teams_notifier.add_event_source(SnsEventSource(kinesis_topic))

        lambda_topic_arn = f'arn:aws:sns:{aws_region}:{aws_account}:stellar-cw-dashboar-stack-LambdaAlarmTopic-1O91TDOEAAFLK'

        lambda_topic = sns.Topic.from_topic_arn(self,
                                                'lambda_topic',
                                                lambda_topic_arn)
        cw_alarm_notification._teams_notifier.add_event_source(SnsEventSource(lambda_topic))
