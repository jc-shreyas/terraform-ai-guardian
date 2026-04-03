output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = aws_subnet.private[*].id
}

output "web_security_group_id" {
  description = "Web security group ID"
  value       = aws_security_group.web.id
}

output "db_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.main.endpoint
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

# ISSUE: Exposing S3 bucket names in outputs can aid attackers
output "app_data_bucket" {
  description = "App data S3 bucket name"
  value       = aws_s3_bucket.app_data.id
}

output "static_site_url" {
  description = "Static website URL"
  value       = aws_s3_bucket_website_configuration.static_site.website_endpoint
}
