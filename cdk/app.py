#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.infrastructure_stack import InfrastructureStack
from stacks.pipeline_stack import PipelineStack

app = cdk.App()

# Get environment from context or default to dev
env_name = app.node.try_get_context("env") or "dev"

# AWS environment
aws_env = cdk.Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region") or "us-east-1"
)

# Create infrastructure stack first
infrastructure_stack = InfrastructureStack(
    app,
    f"DevOpsApp-Infrastructure-{env_name}",
    env_name=env_name,
    env=aws_env
)

# Create pipeline stack
pipeline_stack = PipelineStack(
    app, 
    f"DevOpsApp-Pipeline-{env_name}",
    env_name=env_name,
    env=aws_env
)

# Pipeline depends on infrastructure
pipeline_stack.add_dependency(infrastructure_stack)

app.synth()