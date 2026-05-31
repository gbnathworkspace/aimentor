#!/bin/bash
set -e

fetch() {
  aws ssm get-parameter --name "$1" --with-decryption --query Parameter.Value --output text
}

echo "Fetching secrets from SSM Parameter Store..."

export MONGODB_URI=$(fetch /mentorman/mongodb-uri)
export NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=$(fetch /mentorman/clerk-publishable-key)
export CLERK_SECRET_KEY=$(fetch /mentorman/clerk-secret-key)
export GMAIL_USER=$(fetch /mentorman/gmail-user)
export GMAIL_APP_PASSWORD=$(fetch /mentorman/gmail-app-password)
export VOYAGE_API_KEY=$(fetch voyageapikey)
export ANTHROPIC_API_KEY=$(fetch /claude-proxy/anthropic-api-key)

echo "Secrets loaded. Starting app..."

cd mentorman-app
npm start
