# Photo Uploader - Infrastructure

CloudFormation infrastructure for a containerized photo gallery on ECS Fargate: multi-AZ VPC,
RDS PostgreSQL, a private S3 image bucket served through CloudFront, and a fully automated
ECR-push -> EventBridge -> CodePipeline -> CodeDeploy blue/green deployment pipeline.

Application code lives in a separate repo: https://github.com/arnold-mataba/photo-uploader-app

## Deployment model: nested CloudFormation, no GitSync

All infrastructure is nested CloudFormation (`templates/root.yaml` + child stacks), deployed via
`aws cloudformation package` + `aws cloudformation deploy` from [`.github/workflows/deploy-infra.yml`](.github/workflows/deploy-infra.yml),
authenticated to AWS via OIDC (no long-lived credentials). This is a deliberate departure from
CloudFormation GitSync: GitSync doesn't cleanly support nested-stack templates (child templates
need to already be package-uploaded to S3), and a prior lab found it caused hard-to-diagnose,
console-invisible failures. `package` + `deploy` is idempotent for both first-time creation and
every subsequent update - the same two commands, no separate bootstrap-vs-update path.

## Layout

```
templates/
  root.yaml          # nests everything below, no CloudFormation Exports - params piped down explicitly
  network.yaml         # VPC, 2 public + 2 private subnets (us-east-1a/b), VPC endpoints (no NAT Gateway)
  data.yaml              # RDS PostgreSQL (db.t3.micro) + Secrets Manager credential
  storage-cdn.yaml       # private S3 image bucket + CloudFront (OAC, Price Class 200)
  ecs-alb.yaml             # ECR repo, ECS cluster/service (CodeDeploy-controlled), ALB, Blue/Green target groups, autoscaling
  cicd.yaml                 # EventBridge rule, CodePipeline (V2), CodeDeploy application/deployment group
codedeploy/
  appspec.yaml              # ECS CodeDeploy appspec (literal <TASK_DEFINITION> placeholder)
  taskdef.template.json    # task definition template, rendered with live stack outputs at deploy time
diagram/
  generate_diagram.py       # diagram-as-code (Python `diagrams` package, official AWS icons)
  architecture.png
bootstrap/
  bootstrap.yaml             # one-time: the S3 packaging bucket + the two GitHub OIDC roles
```

## One-time bootstrap (already done for this account)

`bootstrap/bootstrap.yaml` creates the S3 bucket `aws cloudformation package` needs to already
exist, plus two IAM roles trusting the account's existing GitHub OIDC provider:

- `github-actions-cfn-package-photo-uploader` - assumed by this repo's workflow, scoped by
  `sub`/`repository_id`/`repository_owner_id` to `arnold-mataba/photo-uploader-infra`.
- `github-actions-ecr-push-photo-uploader` - assumed by the app repo's workflow, scoped to
  `arnold-mataba/photo-uploader-app`, permissions limited to pushing to the
  `photo-uploader-app` ECR repository.

Deployed once via CLI:

```
aws cloudformation deploy --template-file bootstrap/bootstrap.yaml \
  --stack-name photo-uploader-bootstrap --capabilities CAPABILITY_NAMED_IAM
```

## Design notes

- **No NAT Gateway.** ECS tasks reach ECR/CloudWatch Logs/Secrets Manager via interface VPC
  endpoints and S3 via a gateway endpoint; endpoint security group is scoped to the VPC CIDR
  block (not one resource's SG) so it stays reusable shared infrastructure.
- **ECR repo is `MUTABLE`**, not immutable - an intentional, documented exception. CodePipeline's
  ECR source action watches a stable `latest` tag, which an immutable-tag repo would reject on
  the second push. Every build also pushes an immutable git-SHA tag for provenance.
- **CodePipeline sources are both EventBridge-native** - an ECR source action (emits
  `imageDetail.json`) and an S3 source action reading a `codedeploy-bundle.zip` this repo's own
  deploy workflow renders and uploads on every deploy. No CodeStar Connections GitHub
  integration is used, avoiding its manual console-approval step.
- **CloudFormation never touches the ECS service's task definition after first creation** - the
  service is created once with a placeholder task definition (`DeploymentController: CODE_DEPLOY`),
  and every real deployment thereafter flows exclusively through CodeDeploy blue/green.

## Deliverables

- ALB endpoint: see the `AlbDnsName` output of the `photo-uploader-infra` stack (also printed at
  the end of every `deploy-infra.yml` run).
- Architecture diagram: [`diagram/architecture.png`](diagram/architecture.png)
