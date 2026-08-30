"""
Photo Uploader network/deployment architecture diagram, diagram-as-code.

Follows the standard AWS reference-architecture nesting convention:
AWS Cloud -> Region -> VPC -> Availability Zone -> Subnet, using the
official AWS Architecture Icons set (via the `diagrams` package).
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, ECS, Fargate
from diagrams.aws.database import RDS
from diagrams.aws.devtools import Codedeploy, Codepipeline
from diagrams.aws.general import Users
from diagrams.aws.integration import Eventbridge
from diagrams.aws.network import ALB, CloudFront, InternetGateway, PrivateSubnet, PublicSubnet, VPC
from diagrams.aws.security import SecretsManager
from diagrams.aws.storage import S3

graph_attr = {"fontsize": "14", "bgcolor": "white", "pad": "0.4"}

with Diagram(
    "Photo Uploader - AWS Architecture",
    filename="architecture",
    show=False,
    direction="TB",
    graph_attr=graph_attr,
):
    users = Users("End users")

    with Cluster("AWS Cloud"):
        cdn = CloudFront("CloudFront\n(Price Class 200, OAC)")
        images_bucket = S3("S3: images bucket\n(private, OAC-only)")
        ecr = ECR("ECR: photo-uploader-app")
        pipeline = Codepipeline("CodePipeline (V2)")
        codedeploy = Codedeploy("CodeDeploy\n(ECS blue/green)")
        eventbridge = Eventbridge("EventBridge\n(ECR push rule)")
        secrets = SecretsManager("Secrets Manager\n(RDS credentials)")
        deploy_bucket = S3("S3: infra-deploy bucket\n(pipeline artifacts)")

        with Cluster("Region: us-east-1"):
            with Cluster("VPC 10.0.0.0/16"):
                igw = InternetGateway("Internet Gateway")

                with Cluster("Availability Zone A (us-east-1a)"):
                    with Cluster("Public Subnet A"):
                        pub_a = PublicSubnet("10.0.0.0/24")
                    with Cluster("Private Subnet A"):
                        ecs_a = Fargate("ECS task\n(Fargate)")
                        rds = RDS("RDS PostgreSQL\n(db.t3.micro)")

                with Cluster("Availability Zone B (us-east-1b)"):
                    with Cluster("Public Subnet B"):
                        pub_b = PublicSubnet("10.0.1.0/24")
                    with Cluster("Private Subnet B"):
                        ecs_b = Fargate("ECS task\n(Fargate, scales 1-4)")

                alb = ALB("Application Load Balancer\n(1 listener, Blue/Green target groups)")
                cluster_icon = ECS("ECS Cluster\n(DeploymentController: CODE_DEPLOY)")

    users >> Edge(label="HTTPS") >> cdn
    cdn >> Edge(label="private GetObject via OAC") >> images_bucket
    users >> Edge(label="HTTP", style="dashed") >> alb
    igw >> alb
    alb >> pub_a >> ecs_a
    alb >> pub_b >> ecs_b
    cluster_icon >> Edge(style="dotted") >> [ecs_a, ecs_b]
    ecs_a >> Edge(label="metadata") >> rds
    ecs_a >> Edge(label="upload") >> images_bucket
    ecs_a >> Edge(label="creds", style="dashed") >> secrets

    ecr >> Edge(label="push (latest)", style="bold") >> eventbridge
    eventbridge >> Edge(label="StartPipelineExecution") >> pipeline
    deploy_bucket >> Edge(label="appspec+taskdef", style="dashed") >> pipeline
    pipeline >> codedeploy
    codedeploy >> Edge(label="shift traffic", style="bold") >> alb
