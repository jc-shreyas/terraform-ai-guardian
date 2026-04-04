# CloudWatch monitoring — intentionally missing best practices

resource "aws_cloudwatch_log_group" "app_logs" {
  name = "/app/${var.project_name}"

  # ISSUE: No retention policy — logs grow forever, costs increase
  # ISSUE: No KMS encryption for log data
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project_name}-cpu-high"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "CPUUtilization"
  namespace           = "AWS/EC2"
  period              = 60
  statistic           = "Average"
  threshold           = 90

  # ISSUE: No alarm actions — alert fires but nobody gets notified
  # ISSUE: Only 1 evaluation period — too sensitive, will cause alert fatigue
  # ISSUE: No OK action to auto-resolve
}
