# --- IAM Roles and Policies ---

# ISSUE: Wildcard (*) actions on all resources — admin access disguised as "app role"
resource "aws_iam_role" "app_role" {
  name = "${var.project_name}-app-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-app-role"
  }
}

# ISSUE: Policy grants full admin access — massive security risk
resource "aws_iam_role_policy" "app_policy" {
  name = "${var.project_name}-app-policy"
  role = aws_iam_role.app_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "*"
        Resource = "*"
      }
    ]
  })
}

# ISSUE: Instance profile with the overly-permissive role
resource "aws_iam_instance_profile" "app" {
  name = "${var.project_name}-app-profile"
  role = aws_iam_role.app_role.name
}


# --- CI/CD Pipeline Role ---

# ISSUE: Trust policy allows any account to assume this role (missing condition)
resource "aws_iam_role" "cicd_role" {
  name = "${var.project_name}-cicd-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          AWS = "*"
        }
      }
    ]
  })
}

# ISSUE: CI/CD role has S3, EC2, and IAM permissions — too broad
resource "aws_iam_role_policy" "cicd_policy" {
  name = "${var.project_name}-cicd-policy"
  role = aws_iam_role.cicd_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:*",
          "ec2:*",
          "iam:*",
          "rds:*"
        ]
        Resource = "*"
      }
    ]
  })
}


# --- Hardcoded Credentials (intentional bad practice) ---

# ISSUE: Access keys should NEVER be in Terraform
resource "aws_iam_user" "deploy_user" {
  name = "${var.project_name}-deployer"

  tags = {
    Name = "${var.project_name}-deployer"
  }
}

# ISSUE: Creating static access keys instead of using IAM roles
resource "aws_iam_access_key" "deploy_key" {
  user = aws_iam_user.deploy_user.name
}

# ISSUE: Outputting secret key — it will appear in state file unencrypted
output "deploy_access_key_id" {
  value = aws_iam_access_key.deploy_key.id
}

output "deploy_secret_access_key" {
  value     = aws_iam_access_key.deploy_key.secret
  sensitive = true
}
