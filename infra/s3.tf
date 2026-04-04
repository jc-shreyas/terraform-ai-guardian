# --- S3 Buckets ---

# ISSUE: No encryption configured
# ISSUE: No versioning enabled
# ISSUE: No access logging
resource "aws_s3_bucket" "app_data" {
  bucket = "${var.project_name}-app-data-${var.environment}"

  tags = {
    Name        = "${var.project_name}-app-data"
    Environment = var.environment
  }
}

# ISSUE: Public access is not explicitly blocked
# Missing: aws_s3_bucket_public_access_block
# This means the bucket could be made public accidentally

# ISSUE: No lifecycle rules — data grows forever, costs increase
# Missing: aws_s3_bucket_lifecycle_configuration


# --- Logs Bucket ---

resource "aws_s3_bucket" "logs" {
  bucket = "${var.project_name}-logs-${var.environment}"

  tags = {
    Name        = "${var.project_name}-logs"
    Environment = var.environment
  }
}

# At least this one has versioning
resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ISSUE: Encryption uses default SSE-S3 instead of KMS
resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# ISSUE: Logs bucket also missing public access block


# --- Static Website Bucket ---

# ISSUE: Intentionally public bucket for "static website" — but no CloudFront in front
resource "aws_s3_bucket" "static_site" {
  bucket = "${var.project_name}-static-${var.environment}"

  tags = {
    Name        = "${var.project_name}-static-site"
    Environment = var.environment
  }
}

resource "aws_s3_bucket_website_configuration" "static_site" {
  bucket = aws_s3_bucket.static_site.id

  index_document {
    suffix = "index.html"
  }

  error_document {
    key = "error.html"
  }
}

# ISSUE: Bucket policy allows public read — no CloudFront OAC
resource "aws_s3_bucket_policy" "static_site" {
  bucket = aws_s3_bucket.static_site.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadGetObject"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.static_site.arn}/*"
      }
    ]
  })
}

# --- Backup Bucket ---

resource "aws_s3_bucket" "backups" {
  bucket        = "${var.project_name}-backups-${var.environment}"
  force_destroy = true

  tags = {
    Name = "${var.project_name}-backups"
  }
}

resource "aws_s3_bucket_policy" "backups" {
  bucket = aws_s3_bucket.backups.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowCrossAccountAccess"
        Effect    = "Allow"
        Principal = { AWS = "*" }
        Action    = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource  = "${aws_s3_bucket.backups.arn}/*"
      }
    ]
  })
}
