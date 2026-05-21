variable "aws_region" {
  type        = string
  description = "AWS region to deploy resources"
  default     = "us-east-1"
}

variable "aws_profile" {
  type        = string
  description = "AWS CLI profile name for authentication"
  default     = "julio"
}

variable "environment" {
  type        = string
  description = "Deployment environment name"
  default     = "production"
}

variable "instance_type" {
  type        = string
  description = "EC2 Instance type for the multi-user Windows host"
  default     = "t3.large"
}

variable "key_name" {
  type        = string
  description = "Name of the EC2 Key Pair for administrator login"
  default     = "mt-dev-key"
}

variable "allowed_rdp_cidr" {
  type        = string
  description = "CIDR block allowed to access the host RDP port (3389) directly"
  default     = "38.252.111.234/32"
}

variable "github_repository" {
  type        = string
  description = "The target GitHub repository (format: 'owner/repo') for OIDC federation"
  default     = "devffex/experiment-windows-server-metatrader"
}

variable "cloudflare_token" {
  type        = string
  description = "The Cloudflare Tunnel client token for secure external RDP/API exposure"
  default     = "PLACEHOLDER_CLOUDFLARE_TUNNEL_TOKEN_REPLACE_ME"
  sensitive   = true
}

variable "admin_api_key" {
  type        = string
  description = "Secure admin API key for authenticating Orchestrator deployment updates"
  default     = "PLACEHOLDER_ADMIN_API_KEY_REPLACE_ME"
  sensitive   = true
}

variable "base_domain" {
  type        = string
  description = "The base domain name (e.g. savisor.com) for wildcard routing and DNS"
  default     = "savisor.com"
}
