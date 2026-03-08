terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  required_version = ">= 1.10.0"
}

provider "aws" {
  region                   = var.aws_region
  shared_credentials_files = var.aws_credentials_file
  profile                  = var.aws_profile
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}

# Build Lambda deployment package with dependencies
resource "null_resource" "lambda_build" {
  triggers = {
    requirements = filemd5("${path.module}/../src/requirements.txt")
    source_code  = filemd5("${path.module}/../src/lambda_function.py")
  }

  provisioner "local-exec" {
    command = <<-EOT
      set -e
      cd "${path.module}"
      rm -rf lambda_build
      mkdir -p lambda_build
      pip3 install -r ../src/requirements.txt -t lambda_build --quiet
      cp ../src/lambda_function.py lambda_build/
    EOT
  }
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda_build"
  output_path = "${path.module}/lambda_deployment.zip"

  depends_on = [null_resource.lambda_build]
}

# SSM Parameters for Database Credentials
resource "aws_ssm_parameter" "db_host" {
  name  = "/${var.resource_name}/db_host"
  type  = "String"
  value = var.db_host

  tags = var.tags
}

resource "aws_ssm_parameter" "db_name" {
  name  = "/${var.resource_name}/db_name"
  type  = "String"
  value = var.db_name

  tags = var.tags
}

resource "aws_ssm_parameter" "db_user" {
  name  = "/${var.resource_name}/db_user"
  type  = "String"
  value = var.db_user

  tags = var.tags
}

resource "aws_ssm_parameter" "db_password" {
  name  = "/${var.resource_name}/db_password"
  type  = "SecureString"
  value = var.db_password

  tags = var.tags
}

# IAM Role for Lambda
resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.resource_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = "sts:AssumeRole",
        Effect = "Allow",
        Principal = {
          Service = "lambda.amazonaws.com"
        },
      },
    ],
  })

  tags = var.tags
}

# IAM Policy for Lambda
resource "aws_iam_role_policy" "lambda_execution_policy" {
  name = "${var.resource_name}-lambda-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action = [
          "ssm:GetParameter",
          "ssm:GetParameters"
        ],
        Effect = "Allow",
        Resource = [
          aws_ssm_parameter.db_host.arn,
          aws_ssm_parameter.db_name.arn,
          aws_ssm_parameter.db_user.arn,
          aws_ssm_parameter.db_password.arn
        ]
      },
      {
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Effect   = "Allow",
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.resource_name}*:*"
      }
    ]
  })
}

# Attach VPC execution policy if VPC is configured
resource "aws_iam_role_policy_attachment" "lambda_vpc_execution" {
  count      = var.vpc_subnet_ids != null ? 1 : 0
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Security Group for Lambda (if VPC is used)
resource "aws_security_group" "lambda_sg" {
  count       = var.vpc_id != null ? 1 : 0
  name        = "${var.resource_name}-lambda-sg"
  description = "Security group for Quiz Please Stats Lambda"
  vpc_id      = var.vpc_id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, {
    Name = "${var.resource_name}-lambda-sg"
  })
}

# Lambda Function
resource "aws_lambda_function" "game_stats_collector" {
  description      = "Collect quiz game stats from yerevan.quizplease.ru and store in PostgreSQL"
  function_name    = var.resource_name
  role             = aws_iam_role.lambda_execution_role.arn
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.11"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory


  environment {
    variables = {
      DB_HOST     = var.db_host
      DB_PORT     = var.db_port
      DB_NAME     = var.db_name
      DB_USER     = var.db_user
      DB_PASSWORD = var.db_password
    }
  }

  dynamic "vpc_config" {
    for_each = var.vpc_subnet_ids != null ? [1] : []
    content {
      subnet_ids         = var.vpc_subnet_ids
      security_group_ids = [aws_security_group.lambda_sg[0].id]
    }
  }

  tags = var.tags
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.resource_name}"
  retention_in_days = var.log_retention_days

  tags = var.tags
}

# Lambda Permission for EventBridge
resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.game_stats_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule_rule.arn
}

# EventBridge (CloudWatch Events) Rule for Scheduling
resource "aws_cloudwatch_event_rule" "schedule_rule" {
  name                = "${var.resource_name}-schedule"
  description         = "Trigger Lambda to collect quiz game stats"
  schedule_expression = var.schedule_expression

  tags = var.tags
}

# EventBridge Target
resource "aws_cloudwatch_event_target" "lambda_target" {
  rule      = aws_cloudwatch_event_rule.schedule_rule.name
  target_id = "${var.resource_name}-target"
  arn       = aws_lambda_function.game_stats_collector.arn
}

# SNS Topic for Error Notifications
resource "aws_sns_topic" "lambda_errors" {
  name = "${var.resource_name}-errors"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "lambda_error_email" {
  count     = var.notification_email != "" ? 1 : 0
  topic_arn = aws_sns_topic.lambda_errors.arn
  protocol  = "email"
  endpoint  = var.notification_email
}

# CloudWatch Alarm for Lambda Errors
resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  count               = var.enable_error_alarm ? 1 : 0
  alarm_name          = "${var.resource_name}-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Alert when Lambda function errors occur"
  alarm_actions       = [aws_sns_topic.lambda_errors.arn]

  dimensions = {
    FunctionName = aws_lambda_function.game_stats_collector.function_name
  }

  tags = var.tags
}

# CloudWatch Alarm for Lambda Duration
resource "aws_cloudwatch_metric_alarm" "lambda_duration" {
  count               = var.enable_error_alarm ? 1 : 0
  alarm_name          = "${var.resource_name}-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Maximum"
  threshold           = var.lambda_timeout * 1000 * 0.9 # 90% of timeout
  alarm_description   = "Alert when Lambda function is close to timeout"
  alarm_actions       = [aws_sns_topic.lambda_errors.arn]

  dimensions = {
    FunctionName = aws_lambda_function.game_stats_collector.function_name
  }

  tags = var.tags
}
