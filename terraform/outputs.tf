output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.game_stats_collector.arn
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.game_stats_collector.function_name
}

output "cloudwatch_log_group" {
  description = "CloudWatch Log Group for Lambda"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "eventbridge_rule_name" {
  description = "EventBridge rule name for scheduling"
  value       = aws_cloudwatch_event_rule.schedule_rule.name
}

output "sns_topic_arn" {
  description = "SNS topic ARN for error notifications"
  value       = aws_sns_topic.lambda_errors.arn
}
