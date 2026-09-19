# TerraSentinel-Nepal — Terraform Root Module
# ==============================================
# Provisions the core AWS infrastructure for the demo environment.
# Run: terraform workspace new dev && terraform apply -var-file=environments/dev.tfvars

terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  # Remote state — configure before first apply
  # backend "s3" {
  #   bucket         = "terrasentinel-tfstate"
  #   key            = "terraform.tfstate"
  #   region         = "ap-south-1"
  #   dynamodb_table = "terrasentinel-tfstate-lock"
  #   encrypt        = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "TerraSentinel-Nepal"
      Environment = terraform.workspace
      ManagedBy   = "Terraform"
    }
  }
}

# ── Variables ──────────────────────────────────────────────────────────────────

variable "aws_region" {
  description = "AWS region for all resources"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Short project identifier used in resource names"
  type        = string
  default     = "terrasentinel"
}

# ── S3 Data Bucket ─────────────────────────────────────────────────────────────

resource "aws_s3_bucket" "data" {
  bucket = "${var.project_name}-data-${terraform.workspace}"
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "data_bucket_name" {
  description = "Name of the S3 data bucket"
  value       = aws_s3_bucket.data.id
}
