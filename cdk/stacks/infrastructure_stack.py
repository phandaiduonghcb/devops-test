from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_logs as logs,
    aws_iam as iam,
    aws_ecr as ecr,
    RemovalPolicy,
    Duration
)
from constructs import Construct
import json
import os

class InfrastructureStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, env_name: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.env_name = env_name
        
        # Load environment configurations
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'environments.json')
        with open(config_path, 'r') as f:
            self.env_configs = json.load(f)
        
        config = self.env_configs.get(env_name, self.env_configs["dev"])
        
        # VPC
        self.vpc = self._create_vpc()
        
        # ECS Cluster
        self.cluster = self._create_cluster()
        
        # CloudWatch Log Group
        self.log_group = self._create_log_group()
        
        # ECS Service with ALB
        self.service = self._create_service(config)
    
    def _create_vpc(self):
        """Create VPC with public and private subnets"""
        return ec2.Vpc(
            self, f"DevOpsApp-VPC-{self.env_name}",
            vpc_name=f"devops-app-vpc-{self.env_name}",
            max_azs=2,
            nat_gateways=1,  # Cost optimization - use 1 NAT gateway
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ]
        )
    
    def _create_cluster(self):
        """Create ECS Cluster"""
        return ecs.Cluster(
            self, f"DevOpsApp-Cluster-{self.env_name}",
            cluster_name=f"devops-app-cluster-{self.env_name}",
            vpc=self.vpc,
            container_insights=True
        )
    
    def _create_log_group(self):
        """Create CloudWatch Log Group"""
        return logs.LogGroup(
            self, f"DevOpsApp-LogGroup-{self.env_name}",
            log_group_name=f"/ecs/devops-app-{self.env_name}",
            removal_policy=RemovalPolicy.DESTROY,
            retention=logs.RetentionDays.ONE_WEEK if self.env_name == "dev" else logs.RetentionDays.ONE_MONTH
        )
    
    def _create_service(self, config):
        """Create ECS Service with Application Load Balancer"""
        
        # Task Definition
        task_definition = ecs.FargateTaskDefinition(
            self, f"DevOpsApp-TaskDef-{self.env_name}",
            family=f"devops-app-{self.env_name}",
            memory_limit_mib=config["memory"],
            cpu=config["cpu"]
        )
        
        # Task Execution Role (for pulling images from ECR)
        task_execution_role = iam.Role(
            self, f"DevOpsApp-TaskExecutionRole-{self.env_name}",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AmazonECSTaskExecutionRolePolicy")
            ]
        )
        
        task_definition.add_to_execution_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage"
                ],
                resources=["*"]
            )
        )
        
        # ECR Repository reference
        ecr_repository = ecr.Repository.from_repository_name(
            self, f"DevOpsApp-ECR-{self.env_name}",
            repository_name=f"devops-app-{self.env_name}"
        )
        
        # Container
        container = task_definition.add_container(
            f"devops-app-{self.env_name}",
            container_name=config["container_name"],
            # Reference ECR repository - image tag will be updated by pipeline
            image=ecs.ContainerImage.from_ecr_repository(ecr_repository, "latest"),
            environment={
                "APP_ENV": config["app_env"],
                "APP_NAME": f"devops-app-{self.env_name}",
                "APP_REGION": self.region,
                "APP_PORT": "3000"
            },
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="ecs",
                log_group=self.log_group
            ),
            memory_limit_mib=config["memory"]
        )
        
        # Port mapping
        container.add_port_mappings(
            ecs.PortMapping(
                container_port=3000,
                protocol=ecs.Protocol.TCP,
                name="http"
            )
        )
        
        # Security Group for ALB
        alb_security_group = ec2.SecurityGroup(
            self, f"DevOpsApp-ALB-SG-{self.env_name}",
            vpc=self.vpc,
            description=f"Security group for DevOps App ALB - {self.env_name}",
            allow_all_outbound=True
        )
        
        alb_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow HTTP traffic"
        )
        
        if self.env_name == "prod":
            alb_security_group.add_ingress_rule(
                ec2.Peer.any_ipv4(),
                ec2.Port.tcp(443),
                "Allow HTTPS traffic"
            )
        
        # Security Group for ECS Service
        service_security_group = ec2.SecurityGroup(
            self, f"DevOpsApp-Service-SG-{self.env_name}",
            vpc=self.vpc,
            description=f"Security group for DevOps App ECS Service - {self.env_name}",
            allow_all_outbound=True
        )
        
        service_security_group.add_ingress_rule(
            alb_security_group,
            ec2.Port.tcp(3000),
            "Allow traffic from ALB"
        )

        # Get created certificate
        # certificate = acm.Certificate.from_certificate_arn(
        #     self, "MyCert",
        #     "arn:aws:acm:us-east-1:123456789012:certificate/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxx"
        # )

        
        # Application Load Balanced Fargate Service
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self, f"DevOpsApp-Service-{self.env_name}",
            service_name=f"devops-app-service-{self.env_name}",
            cluster=self.cluster,
            task_definition=task_definition,
            desired_count=config["desired_count"],
            listener_port=80, # 443 for https
            # certificate=certificate, # Assign certificate                      
            public_load_balancer=True,
            platform_version=ecs.FargatePlatformVersion.LATEST,
            security_groups=[alb_security_group],
            task_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            )
        )
        
        # Configure health check
        service.target_group.configure_health_check(
            path="/healthcheck",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3
        )
        
        # Auto Scaling
        scalable_target = service.service.auto_scale_task_count(
            min_capacity=config["desired_count"],
            max_capacity=config["desired_count"] * 3
        )
        
        # CPU-based scaling
        scalable_target.scale_on_cpu_utilization(
            f"DevOpsApp-CPUScaling-{self.env_name}",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )
        
        # Memory-based scaling
        scalable_target.scale_on_memory_utilization(
            f"DevOpsApp-MemoryScaling-{self.env_name}",
            target_utilization_percent=80,
            scale_in_cooldown=Duration.minutes(5),
            scale_out_cooldown=Duration.minutes(2)
        )
        
        return service