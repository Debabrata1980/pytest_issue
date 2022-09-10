#!/usr/bin/env python3

from git import Repo
from aws_cdk import core
from stellar_stream.stellar_stream_stack import StellarStreamStack
from stack_params import PARAMS


repo = Repo(".", search_parent_directories=True)

branch = str(repo.active_branch)
print(f'On branch {branch}')
branch = branch if branch in PARAMS else 'dev'

if branch in PARAMS:
    app = core.App()
    StellarStreamStack(app, PARAMS[branch]["stack_name"], PARAMS[branch])
    app.synth()
else:
    print(f"The specified environment '{branch}' doesn't exist in the stack_params. Stack deployment failed.")
