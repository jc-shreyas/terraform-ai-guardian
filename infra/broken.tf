# Intentionally broken Terraform to trigger pipeline failure

resource "aws_s3_bucket" "test" {
  bucket = "${var.project_name}-test"

  # Invalid argument — this doesn't exist on aws_s3_bucket
  enable_acceleration = true

  # Reference to undeclared resource
  depends_on = [aws_iam_role.nonexistent_role]
}

resource "aws_security_group_rule" "bad_rule" {
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  # Missing required argument: security_group_id
}
