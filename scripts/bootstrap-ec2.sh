#!/usr/bin/env bash
# One-time setup for the EC2 instance (Amazon Linux 2 or 2023).
# Run as ec2-user after the instance launches; Docker must not be installed yet.
set -euo pipefail

# Detect distro
if grep -qi "Amazon Linux release 2023" /etc/os-release 2>/dev/null; then
  DISTRO="al2023"
elif grep -qi "Amazon Linux 2" /etc/os-release 2>/dev/null; then
  DISTRO="al2"
else
  echo "Unsupported OS. Script targets Amazon Linux 2 or 2023." >&2
  exit 1
fi

echo "Detected: $DISTRO"

# ── Install Docker ────────────────────────────────────────────────────────────
if [ "$DISTRO" = "al2023" ]; then
  sudo dnf update -y
  sudo dnf install -y docker aws-cli
else
  sudo yum update -y
  sudo amazon-linux-extras install docker -y
  sudo yum install -y aws-cli
fi

sudo systemctl enable --now docker
sudo usermod -aG docker ec2-user

echo ""
echo "Docker installed. Log out and back in (or run 'newgrp docker') so the"
echo "group change takes effect, then verify with: docker run hello-world"
echo ""

# ── Confirm AWS CLI is available ──────────────────────────────────────────────
aws --version

echo ""
echo "Bootstrap complete. Ensure this EC2 instance has an IAM role attached"
echo "with the following SSM permissions:"
echo "  ssm:GetParameter on:"
echo "    /mentorman/mongodb-uri"
echo "    /mentorman/clerk-issuer  (optional)"
echo "    /claude-proxy/anthropic-api-key"
echo "    /voyageapikey"
echo ""
echo "The deploy pipeline will SSH in as ec2-user and use these permissions"
echo "to fetch secrets at deploy time — no credentials on disk."
