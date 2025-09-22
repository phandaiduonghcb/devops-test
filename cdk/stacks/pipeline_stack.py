from aws_cdk import (
    Stack,
    aws_codepipeline as codepipeline,
    aws_codepipeline_actions as codepipeline_actions,
    aws_codebuild as codebuild,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_s3 as s3,
    RemovalPolicy,
    SecretValue
)
from constructs import Construct
import json
import os

class PipelineStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, env_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.env_name = env_name
        
        # Load environment configurations
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'environments.json')
        with open(config_path, 'r') as f:
            self.env_configs = json.load(f)
        
        config = self.env_configs.get(env_name, self.env_configs["dev"])
        
        # S3 Bucket for artifacts
        self.artifacts_bucket = s3.Bucket(
            self, f"DevOpsApp-Artifacts-{env_name}",
            bucket_name=f"devops-app-artifacts-{env_name}-{self.account}",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )
        
        # ECR Repository
        self.ecr_repo = ecr.Repository(
            self, f"DevOpsApp-ECR-{env_name}",
            repository_name=f"devops-app-{env_name}",
            removal_policy=RemovalPolicy.DESTROY
        )
        
        # CodeBuild Projects
        self.build_project = self._create_build_project(config)
        self.test_project = self._create_test_project(config)
        self.deploy_project = self._create_deploy_project(config)
        
        # CodePipeline
        self.pipeline = self._create_pipeline(config)
    
    def _create_build_project(self, config):
        """Create CodeBuild project for building and pushing Docker image to ECR"""
        build_role = iam.Role(
            self, f"DevOpsApp-BuildRole-{self.env_name}",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryPowerUser")
            ]
        )
        
        # Add S3 permissions for artifacts
        build_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                resources=[f"{self.artifacts_bucket.bucket_arn}/*"]
            )
        )
        
        return codebuild.Project(
            self, f"DevOpsApp-Build-{self.env_name}",
            project_name=f"devops-app-build-{self.env_name}",
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "echo Logging in to Amazon ECR...",
                            "aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com",
                            "REPOSITORY_URI=$AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$IMAGE_REPO_NAME",
                            "COMMIT_HASH=$(echo $CODEBUILD_RESOLVED_SOURCE_VERSION | cut -c 1-7)",
                            "IMAGE_TAG=${COMMIT_HASH:=latest}"
                        ]
                    },
                    "build": {
                        "commands": [
                            "echo Build started on `date`",
                            "echo Building the Docker image...",
                            "docker build -t $IMAGE_REPO_NAME:$IMAGE_TAG .",
                            "docker tag $IMAGE_REPO_NAME:$IMAGE_TAG $REPOSITORY_URI:$IMAGE_TAG",
                            "docker tag $IMAGE_REPO_NAME:$IMAGE_TAG $REPOSITORY_URI:latest"
                        ]
                    },
                    "post_build": {
                        "commands": [
                            "echo Build completed on `date`",
                            "echo Pushing the Docker images...",
                            "docker push $REPOSITORY_URI:$IMAGE_TAG",
                            "docker push $REPOSITORY_URI:latest",
                            "echo Writing image definitions file...",
                            f'printf \'[{{"name":"{config["container_name"]}","imageUri":"%s"}}]\' $REPOSITORY_URI:$IMAGE_TAG > imagedefinitions.json',
                            "cat imagedefinitions.json"
                        ]
                    }
                },
                "artifacts": {
                    "files": [
                        "imagedefinitions.json",
                        "docker-compose.yml",
                        "pyproject.toml",
                        "poetry.lock"
                    ]
                }
            }),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=True,
                environment_variables={
                    "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                    "AWS_ACCOUNT_ID": codebuild.BuildEnvironmentVariable(value=self.account),
                    "IMAGE_REPO_NAME": codebuild.BuildEnvironmentVariable(value=self.ecr_repo.repository_name)
                }
            ),
            role=build_role
        )
    
    def _create_test_project(self, config):
        """Create CodeBuild project for running tests with Docker Compose"""
        test_role = iam.Role(
            self, f"DevOpsApp-TestRole-{self.env_name}",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly")
            ]
        )
        
        # Add S3 permissions for artifacts
        test_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject"
                ],
                resources=[f"{self.artifacts_bucket.bucket_arn}/*"]
            )
        )
        
        return codebuild.Project(
            self, f"DevOpsApp-Test-{self.env_name}",
            project_name=f"devops-app-test-{self.env_name}",
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "echo Logging in to Amazon ECR...",
                            "aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com",
                            "echo Getting image URI from build artifacts...",
                            "IMAGE_URI=$(cat imagedefinitions.json | python3 -c \"import sys, json; print(json.load(sys.stdin)[0]['imageUri'])\")",
                            "echo Image URI: $IMAGE_URI",
                            "echo Pulling Docker image...",
                            "docker pull $IMAGE_URI"
                        ]
                    },
                    "build": {
                        "commands": [
                            "echo Test started on `date`",
                            "echo Running tests with Docker image override...",
                            "docker run --rm $IMAGE_URI poetry run pytest -s",
                            "echo Tests completed successfully"
                        ]
                    },
                    "post_build": {
                        "commands": [
                            "echo Test completed on `date`"
                        ]
                    }
                }
            }),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                privileged=True,
                environment_variables={
                    "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                    "AWS_ACCOUNT_ID": codebuild.BuildEnvironmentVariable(value=self.account),
                    "IMAGE_REPO_NAME": codebuild.BuildEnvironmentVariable(value=self.ecr_repo.repository_name)
                }
            ),
            role=test_role
        )
    
    def _create_deploy_project(self, config):
        """Create CodeBuild project for deploying to ECS using imagedefinitions.json"""
        deploy_role = iam.Role(
            self, f"DevOpsApp-DeployRole-{self.env_name}",
            assumed_by=iam.ServicePrincipal("codebuild.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonECS_FullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonEC2ContainerRegistryReadOnly")
            ]
        )
        
        # Add inline policy for ECS service update and task definition
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecs:UpdateService",
                    "ecs:DescribeServices",
                    "ecs:DescribeTaskDefinition",
                    "ecs:RegisterTaskDefinition",
                    "iam:PassRole"
                ],
                resources=["*"]
            )
        )
        
        # Add S3 permissions for artifacts
        deploy_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject"
                ],
                resources=[f"{self.artifacts_bucket.bucket_arn}/*"]
            )
        )
        
        return codebuild.Project(
            self, f"DevOpsApp-Deploy-{self.env_name}",
            project_name=f"devops-app-deploy-{self.env_name}",
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "echo Deploy started on `date`",
                            "echo Checking imagedefinitions.json...",
                            "cat imagedefinitions.json",
                            "IMAGE_URI=$(cat imagedefinitions.json | python3 -c \"import sys, json; print(json.load(sys.stdin)[0]['imageUri'])\")",
                            "echo Image URI: $IMAGE_URI"
                        ]
                    },
                    "build": {
                        "commands": [
                            f"echo Updating ECS service {config['service_name']} in cluster {config['cluster_name']}...",
                            f"echo Getting current task definition for service {config['service_name']}...",
                            f"TASK_DEFINITION=$(aws ecs describe-services --cluster {config['cluster_name']} --services {config['service_name']} --query 'services[0].taskDefinition' --output text)",
                            f"echo Current task definition: $TASK_DEFINITION",
                            f"echo Creating new task definition with updated image...",
                            f"aws ecs describe-task-definition --task-definition $TASK_DEFINITION --query 'taskDefinition' > task-def.json",
                            f"python3 -c \"import json; td=json.load(open('task-def.json')); td['containerDefinitions'][0]['image']='$IMAGE_URI'; [td.pop(k, None) for k in ['taskDefinitionArn', 'revision', 'status', 'requiresAttributes', 'placementConstraints', 'compatibilities', 'registeredAt', 'registeredBy']]; json.dump(td, open('new-task-def.json', 'w'), indent=2)\"",
                            f"echo Registering new task definition...",
                            f"NEW_TASK_DEF_ARN=$(aws ecs register-task-definition --cli-input-json file://new-task-def.json --query 'taskDefinition.taskDefinitionArn' --output text)",
                            f"echo New task definition ARN: $NEW_TASK_DEF_ARN",
                            f"echo Updating ECS service with new task definition...",
                            f"aws ecs update-service --cluster {config['cluster_name']} --service {config['service_name']} --task-definition $NEW_TASK_DEF_ARN",
                            f"echo Waiting for service {config['service_name']} to become stable...",
                            f"aws ecs wait services-stable --cluster {config['cluster_name']} --services {config['service_name']} --region $AWS_DEFAULT_REGION"
                        ]
                    },
                    "post_build": {
                        "commands": [
                            "echo Deploy completed on `date`",
                            f"echo Service {config['service_name']} updated successfully"
                        ]
                    }
                }
            }),
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                environment_variables={
                    "AWS_DEFAULT_REGION": codebuild.BuildEnvironmentVariable(value=self.region),
                    "AWS_ACCOUNT_ID": codebuild.BuildEnvironmentVariable(value=self.account),
                    "IMAGE_REPO_NAME": codebuild.BuildEnvironmentVariable(value=self.ecr_repo.repository_name)
                }
            ),
            role=deploy_role
        )
    
    def _create_pipeline(self, config):
        """Create the complete CI/CD pipeline"""
        # Source artifact
        source_output = codepipeline.Artifact("SourceOutput")
        
        # Build artifact  
        build_output = codepipeline.Artifact("BuildOutput")
        
        # Test artifact
        test_output = codepipeline.Artifact("TestOutput")
        
        # Pipeline
        pipeline = codepipeline.Pipeline(
            self, f"DevOpsApp-Pipeline-{self.env_name}",
            pipeline_name=f"devops-app-{self.env_name}",
            artifact_bucket=self.artifacts_bucket,
            stages=[
                # Source Stage
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[
                        codepipeline_actions.GitHubSourceAction(
                            action_name="GitHub_Source",
                            owner="phandaiduonghcb",  # Replace with your GitHub username
                            repo="devops-test",         # Replace with your repo name
                            branch=config["branch"],
                            oauth_token=SecretValue.secrets_manager("github-token"),
                            output=source_output,
                            trigger=codepipeline_actions.GitHubTrigger.POLL
                        )
                    ]
                ),
                # Build Stage
                codepipeline.StageProps(
                    stage_name="Build",
                    actions=[
                        codepipeline_actions.CodeBuildAction(
                            action_name="Build_Docker_Image",
                            project=self.build_project,
                            input=source_output,
                            outputs=[build_output]
                        )
                    ]
                ),
                # Test Stage
                codepipeline.StageProps(
                    stage_name="Test",
                    actions=[
                        codepipeline_actions.CodeBuildAction(
                            action_name="Run_Tests",
                            project=self.test_project,
                            input=build_output,  # Use build output to get imagedefinitions.json
                            outputs=[test_output]
                        )
                    ]
                ),
                # Deploy Stage
                codepipeline.StageProps(
                    stage_name="Deploy",
                    actions=[
                        codepipeline_actions.CodeBuildAction(
                            action_name="Deploy_to_ECS",
                            project=self.deploy_project,
                            input=build_output
                        )
                    ]
                )
            ]
        )
        
        return pipeline