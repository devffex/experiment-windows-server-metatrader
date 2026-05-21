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
