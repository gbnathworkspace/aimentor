# EC2 Deployment Guide — layered-memory-service

This guide covers deploying the service as a Docker container on an AWS EC2 instance.
Secrets (MongoDB URI, Voyage API key, internal API key) are pulled from AWS SSM Parameter Store
at startup — nothing sensitive is passed as a plain environment variable or baked into the image.

---

## Prerequisites

### EC2 Instance
- OS: Ubuntu 22.04 LTS or Amazon Linux 2
- Instance type: t3.small or larger
- IAM role attached with the following policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:GetParameter",
      "Resource": [
        "arn:aws:ssm:<region>:<account-id>:parameter/mentorman/mongodb-uri",
        "arn:aws:ssm:<region>:<account-id>:parameter/voyageapikey",
        "arn:aws:ssm:<region>:<account-id>:parameter/layered-memory-service/api-key"
      ]
    }
  ]
}
```

### AWS SSM Parameters (create these before deploying)

| SSM Path | Type | Description |
|----------|------|-------------|
| `/mentorman/mongodb-uri` | SecureString | MongoDB Atlas connection string |
| `voyageapikey` | SecureString | Voyage AI API key |
| `/layered-memory-service/api-key` | SecureString | Internal shared API key for `X-API-Key` header |

---

## Step 1 — Install Docker on EC2

**Ubuntu:**
```bash
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
# Logout and log back in for the group change to take effect
```

**Amazon Linux 2:**
```bash
sudo yum update -y
sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker
sudo usermod -aG docker $USER
# Logout and log back in
```

---

## Step 2 — Clone the Repository

```bash
git clone https://github.com/gbnathworkspace/layered-memory-service.git
cd layered-memory-service
```

---

## Step 3 — Build the Docker Image

```bash
docker build -t layered-memory-service .
```

---

## Step 4 — Run the Container

```bash
docker run -d \
  --name layered-memory \
  --restart unless-stopped \
  -p 8000:8000 \
  -e APP_ENV=production \
  -e AWS_REGION=ap-south-1 \
  -e DB_SSM_PARAM_NAME=/mentorman/mongodb-uri \
  -e MONGODB_DB_NAME=layered_memory \
  -e LOG_LEVEL=INFO \
  -e PORT=8000 \
  layered-memory-service
```

> `--restart unless-stopped` ensures the container auto-restarts on crash or EC2 reboot.
> The container fetches all secrets from SSM using the EC2 instance role — no credentials in the command.

---

## Step 5 — Verify

```bash
# Health check
curl http://localhost:8000/health
# Expected: {"status": "ok"}

# Container logs (check SSM secret loading + MongoDB connection)
docker logs layered-memory

# Live log tail
docker logs -f layered-memory
```

---

## Updating to a New Version

```bash
cd layered-memory-service
git pull origin main
docker build -t layered-memory-service .
docker stop layered-memory && docker rm layered-memory
docker run -d \
  --name layered-memory \
  --restart unless-stopped \
  -p 8000:8000 \
  -e APP_ENV=production \
  -e AWS_REGION=ap-south-1 \
  -e DB_SSM_PARAM_NAME=/mentorman/mongodb-uri \
  -e MONGODB_DB_NAME=layered_memory \
  -e LOG_LEVEL=INFO \
  -e PORT=8000 \
  layered-memory-service
```

---

## Common Operations

```bash
# Stop the container
docker stop layered-memory

# Start it again
docker start layered-memory

# Restart
docker restart layered-memory

# View running containers
docker ps

# Remove container (image is preserved)
docker rm layered-memory

# Remove image (to force a clean rebuild)
docker rmi layered-memory-service
```

---

## Troubleshooting

**Container exits immediately on startup**
```bash
docker logs layered-memory
```
Most likely cause: SSM parameter not found (wrong path or missing IAM permission).
Check that the SSM paths match exactly what's in `app/core/config.py`.

**`botocore.exceptions.NoCredentialsError`**
The EC2 instance role is not attached or does not have `ssm:GetParameter` permission.
Go to EC2 console → Instance → Actions → Security → Modify IAM role.

**MongoDB connection refused**
Verify the MongoDB Atlas connection string stored in SSM is correct and that the Atlas
IP allowlist includes the EC2 instance's public IP (or use a VPC peering / private endpoint).

**Port 8000 not reachable from outside**
Check the EC2 security group — inbound rule for TCP port 8000 must allow traffic from
your intended source (load balancer, specific IP, or `0.0.0.0/0` for public access).

---

## Security Notes

- The `.env` file is gitignored and must **never** be committed.
- Secrets live exclusively in AWS SSM SecureString parameters (AES-256 encrypted at rest).
- The container inherits the EC2 instance profile via the metadata service (`169.254.169.254`) — no long-lived credentials anywhere.
- Restrict port 8000 in the security group to your ALB or internal network rather than exposing it publicly.
