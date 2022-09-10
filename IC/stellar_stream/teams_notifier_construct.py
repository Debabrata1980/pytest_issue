from aws_cdk import core
import aws_cdk.aws_lambda as lmb


class TeamsNotifier(core.Construct):

    @property
    def handler(self):
        return self._teams_notifier

    def __init__(self, scope: core.Construct, id: str) -> None:
        super().__init__(scope, id)

        self._teams_notifier = lmb.Function(self, 'TeamsNotifier', runtime=lmb.Runtime.PYTHON_3_7,
                                            code=lmb.Code.from_asset('teams_notifier'),
                                            handler='index.lambda_handler',)
