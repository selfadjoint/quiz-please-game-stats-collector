variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "eu-central-1"
}

variable "aws_credentials_file" {
  description = "Path to AWS credentials file"
  type        = list(string)
  default     = ["~/.aws/credentials"]
}

variable "aws_profile" {
  description = "AWS profile to use"
  type        = string
  default     = "default"
}

variable "resource_name" {
  description = "Name prefix for all resources"
  type        = string
  default     = "quiz-please-stats-collector"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "QuizPleaseStats"
    Environment = "production"
    ManagedBy   = "Terraform"
  }
}

# Database Configuration
variable "db_host" {
  description = "PostgreSQL database host"
  type        = string
}

variable "db_port" {
  description = "PostgreSQL database port"
  type        = string
  default     = "5432"
}

variable "db_name" {
  description = "PostgreSQL database name"
  type        = string
}

variable "db_user" {
  description = "PostgreSQL database user"
  type        = string
}

variable "db_password" {
  description = "PostgreSQL database password"
  type        = string
  sensitive   = true
}

# Lambda Configuration
variable "lambda_timeout" {
  description = "Lambda function timeout in seconds"
  type        = number
  default     = 600
}

variable "lambda_memory" {
  description = "Lambda function memory in MB"
  type        = number
  default     = 512
}

variable "schedule_expression" {
  description = "EventBridge schedule expression (cron or rate)"
  type        = string
  default     = "cron(0 3 * * ? *)" # Run daily at 3 AM UTC
}

# VPC Configuration (optional)
variable "vpc_id" {
  description = "VPC ID for Lambda (if database is in VPC)"
  type        = string
  default     = null
}

variable "vpc_subnet_ids" {
  description = "Subnet IDs for Lambda (if database is in VPC)"
  type        = list(string)
  default     = null
}

# Monitoring Configuration
variable "notification_email" {
  description = "Email address for error notifications"
  type        = string
  default     = ""
}

variable "enable_error_alarm" {
  description = "Enable CloudWatch alarms for errors"
  type        = bool
  default     = true
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days"
  type        = number
  default     = 14
}
