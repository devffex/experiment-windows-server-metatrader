# ==============================================================================
# S3 Deployment Artifacts Bucket (For Wheels and deployment updates)
# ==============================================================================

resource "aws_s3_bucket" "deploy_bucket" {
  bucket        = "savisor-${var.environment}-deploy-bucket"
  force_destroy = true # Safe to cleanup on teardown in dev/staging environments

  tags = {
    Name        = "Savisor Deployment Bucket"
    Environment = var.environment
  }
}

# Block public access to the deployment bucket
resource "aws_s3_bucket_public_access_block" "deploy_bucket_block" {
  bucket = aws_s3_bucket.deploy_bucket.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# ==============================================================================
# AWS Systems Manager (SSM) Parameter Store Definitions
# ==============================================================================

resource "aws_ssm_parameter" "cloudflare_token" {
  name        = "/savisor/${var.environment}/cloudflare_token"
  type        = "SecureString"
  value       = "PLACEHOLDER_CLOUDFLARE_TUNNEL_TOKEN_REPLACE_ME"
  description = "Cloudflare Zero Trust Secure Tunnel Token"

  lifecycle {
    ignore_changes = [value] # Prevent subsequent Terraform runs from overwriting manual token updates
  }

  tags = {
    Environment = var.environment
  }
}

resource "aws_ssm_parameter" "orchestrator_settings" {
  name        = "/savisor/${var.environment}/orchestrator_settings"
  type        = "String"
  value       = jsonencode({
    base_dir           = "C:\\savisor"
    port_range_start   = 8001
    port_range_end     = 8100
    rdp_server_address = "localhost"
  })
  description = "JSON configuration settings for the Savisor Central Orchestrator service"

  tags = {
    Environment = var.environment
  }
}
