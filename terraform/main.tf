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

    # 3. Create temp execution paths
    $TempPath = "C:\savisor\temp"
    if (-not (Test-Path $TempPath)) {
        New-Item -ItemType Directory -Path $TempPath -Force | Out-Null
    }

    # 4. Fetch the bootstrapping script from the public repository
    $BootstrapUrl = "https://raw.githubusercontent.com/devffex/experiment-windows-server-metatrader/main/bootstrap-server.ps1"
    $LocalBootstrap = "$TempPath\bootstrap-server.ps1"

    try {
        Invoke-WebRequest -Uri $BootstrapUrl -OutFile $LocalBootstrap -UseBasicParsing -TimeoutSec 60
    } catch {
        Write-Output "Failed to fetch bootstrap script from GitHub: $_"
    }

    # 5. Retrieve the Cloudflare Tunnel token securely from AWS Parameter Store
    $CfToken = ""
    try {
        # Check if AWS PowerShell modules are loaded (standard on EC2 Windows AMIs)
        Import-Module AWSPowerShell -ErrorAction SilentlyContinue
        $CfToken = (Get-SSMParameter -Name "/savisor/${var.environment}/cloudflare_token" -WithDecryption).Value
    } catch {
        Write-Output "Failed to retrieve SSM cloudflare_token: $_"
    }

    # 6. Run the bootstrapping script
    if (Test-Path $LocalBootstrap) {
        $LogFile = "$TempPath\userdata-bootstrap.log"
        if ($CfToken -and $CfToken -ne "PLACEHOLDER_CLOUDFLARE_TUNNEL_TOKEN_REPLACE_ME") {
            Write-Output "Bootstrapping server with retrieved Cloudflare Token..." >> $LogFile
            powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LocalBootstrap -CloudflareToken $CfToken >> $LogFile 2>&1
        } else {
            Write-Output "Bootstrapping server without Cloudflare Token (placeholder present)..." >> $LogFile
            powershell.exe -NoProfile -ExecutionPolicy Bypass -File $LocalBootstrap >> $LogFile 2>&1
        }
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
