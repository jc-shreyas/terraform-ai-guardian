# --- RDS Database ---

# ISSUE: Publicly accessible database
# ISSUE: No encryption at rest
# ISSUE: No multi-AZ for production
# ISSUE: No deletion protection
# ISSUE: Short backup retention
# ISSUE: Hardcoded credentials in plain text
resource "aws_db_instance" "main" {
  identifier     = "${var.project_name}-db-${var.environment}"
  engine         = "mysql"
  engine_version = "8.0"
  instance_class = "db.t3.large"    # ISSUE: Possibly oversized for workload

  allocated_storage     = 100
  max_allocated_storage = 1000      # ISSUE: No alert before auto-scaling hits 1TB

  db_name  = "appdb"
  username = "admin"
  password = "SuperSecret123!"     # CRITICAL: Hardcoded password in plain text

  vpc_security_group_ids = [aws_security_group.database.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  publicly_accessible  = true       # CRITICAL: Database exposed to internet
  storage_encrypted    = false      # CRITICAL: Data at rest not encrypted
  multi_az             = false      # ISSUE: No HA for production
  deletion_protection  = false      # ISSUE: Can be deleted accidentally

  backup_retention_period = 1       # ISSUE: Only 1 day of backups
  skip_final_snapshot     = true    # ISSUE: No final snapshot on deletion

  # ISSUE: No performance insights enabled
  # ISSUE: No enhanced monitoring
  # ISSUE: No CloudWatch alarms

  tags = {
    Name        = "${var.project_name}-db"
    Environment = var.environment
  }
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project_name}-db-subnet"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-db-subnet"
  }
}


# --- ElastiCache (Redis) ---

# ISSUE: No encryption in transit
# ISSUE: No auth token
# ISSUE: Single node (no replication)
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project_name}-redis"
  engine               = "redis"
  node_type            = "cache.t3.medium"
  num_cache_nodes      = 1                      # ISSUE: Single node, no failover
  port                 = 6379

  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.database.id]  # ISSUE: Reusing DB security group

  # ISSUE: No snapshot/backup configured
  # ISSUE: No at-rest encryption
  # ISSUE: No in-transit encryption
  # ISSUE: No auto minor version upgrade

  tags = {
    Name = "${var.project_name}-redis"
  }
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project_name}-redis-subnet"
  subnet_ids = aws_subnet.private[*].id
}
