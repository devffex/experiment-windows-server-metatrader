# ==============================================================================
# AWS Configuration and Provider
# ==============================================================================

terraform {
  required_version = ">= 1.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile
}

# ==============================================================================
# Security Group Layouts
# ==============================================================================

resource "aws_security_group" "host_sg" {
  name        = "savisor-${var.environment}-security-group"
  description = "Security firewall rules for the Savisor Multi-User MetaTrader Host"

  # Outbound rules: Open to allow outgoing Cloudflare Tunnel connections & script installers
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/32"] # Safely restricts, but open to 0.0.0.0/0 for downloading silent setups
    self        = false
  }

  # Inbound RDP access: Strictly locked down to the specified developer CIDR block
  ingress {
    from_port   = 3389
    to_port     = 3389
    protocol    = "tcp"
    cidr_blocks = [var.allowed_rdp_cidr]
    description = "Admin Direct Remote Desktop Port Lockdown"
  }

  # Inbound API (8000) is completely BLOCKED. Access is only allowed via outbound Cloudflare Tunnel!

  tags = {
    Name        = "Savisor Host Security Group"
    Environment = var.environment
  }
}

# Add standard egress rule override to allow outbound downloading of installers
resource "aws_security_group_rule" "allow_all_egress" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.host_sg.id
}

# ==============================================================================
# Windows Server 2022 AMI Resolution
# ==============================================================================

data "aws_ami" "windows_server" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["Windows_Server-2022-English-Full-Base-*"]
  }

  filter {
    name   = "state"
    values = ["available"]
  }
}

# ==============================================================================
# Windows Server EC2 Host Provisioning
# ==============================================================================

resource "aws_instance" "host_instance" {
  ami                  = data.aws_ami.windows_server.id
  instance_type        = var.instance_type
  key_name             = var.key_name
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name

  vpc_security_group_ids = [aws_security_group.host_sg.id]

  # Allocate robust, enterprise-grade EBS gp3 block storage
  root_block_device {
    volume_size           = 40
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = {
      Name = "Savisor Host Root Disk"
    }
  }

  # Dynamic first-boot script to trigger global server bootstrapping
  user_data = <<-EOF
    <powershell>
    # 1. Wait for system initialization & network connectivity
    Start-Sleep -Seconds 20

    # 2. Establish TLS 1.2
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    # 3. Create temp and system execution paths
    $SavisorDir = "C:\savisor"
    $TempPath = "$SavisorDir\temp"
    if (-not (Test-Path $TempPath)) {
        New-Item -ItemType Directory -Path $TempPath -Force | Out-Null
    }

    # 4. Generate local .env file using variables injected at build time by Terraform
    $EnvContent = @(
        "CLOUDFLARE_TUNNEL_TOKEN=${var.cloudflare_token}",
        "ORCHESTRATOR_ADMIN_API_KEY=${var.admin_api_key}",
        "ORCHESTRATOR_BASE_DOMAIN=${var.base_domain}",
        "GITHUB_REPOSITORY=${var.github_repository}"
    )
    $EnvContent | Out-File -FilePath "$SavisorDir\.env" -Encoding utf8 -Force

    # Secure the environment configuration file immediately
    $Acl = Get-Acl "$SavisorDir\.env"
    $Acl.SetAccessRuleProtection($true, $false)
    $SysRule = New-Object System.Security.AccessControl.FileSystemAccessRule("SYSTEM", "FullControl", "Allow")
    $AdminRule = New-Object System.Security.AccessControl.FileSystemAccessRule("Administrators", "FullControl", "Allow")
    $Acl.SetAccessRule($SysRule)
    $Acl.SetAccessRule($AdminRule)
    Set-Acl "$SavisorDir\.env" $Acl

    # 5. Fetch the bootstrapping script from the public repository
    $BootstrapUrl = "https://raw.githubusercontent.com/${var.github_repository}/main/bootstrap-server.ps1"
    $LocalBootstrap = "$TempPath\bootstrap-server.ps1"

    try {
        Invoke-WebRequest -Uri $BootstrapUrl -OutFile $LocalBootstrap -UseBasicParsing -TimeoutSec 60
    } catch {
        Write-Output "Failed to fetch bootstrap script from GitHub: $_"
    }

    # 6. Run the bootstrapping script
    if (Test-Path $LocalBootstrap) {
        $LogFile = "$TempPath\userdata-bootstrap.log"
        Write-Output "Bootstrapping server with cloud-agnostic secure environment..." >> $LogFile
        powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LocalBootstrap -EnvPath "$SavisorDir\.env" >> $LogFile 2>&1
    } else {
        Write-Output "ERROR: bootstrap-server.ps1 could not be downloaded." >> C:\savisor\temp\error.log
    }
    </powershell>
  EOF

  tags = {
    Name        = "Savisor-MT5-Production-Host"
    Environment = var.environment
  }
}
