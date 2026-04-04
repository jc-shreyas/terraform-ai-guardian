variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-southeast-2"  # Sydney — relevant for Australian job market
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "devops-demo"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "instance_type" {
  description = "EC2 instance type for web servers"
  type        = string
  default     = "t3.micro"
}

variable "tags" {
  description = "Default tags for all resources"
  type        = map(string)
  default     = {
    ManagedBy = "terraform"
    Project   = "devops-demo"
  }
}
