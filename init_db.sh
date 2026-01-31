#!/bin/bash
# Database initialization script

set -e

echo "==================================="
echo "Database Initialization"
echo "==================================="
echo ""

# Check if psql is installed
if ! command -v psql &> /dev/null; then
    echo "❌ psql is not installed. Please install PostgreSQL client"
    exit 1
fi

# Read database connection details
read -p "Database host: " DB_HOST
read -p "Database port [5432]: " DB_PORT
DB_PORT=${DB_PORT:-5432}
read -p "Database name: " DB_NAME
read -p "Database user: " DB_USER
read -sp "Database password: " DB_PASSWORD
echo ""
echo ""

# Test connection
echo "Testing database connection..."
export PGPASSWORD="$DB_PASSWORD"

if psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT version();" > /dev/null 2>&1; then
    echo "✅ Connection successful"
else
    echo "❌ Connection failed. Please check your credentials."
    exit 1
fi

# Run DDL script
echo ""
echo "Creating database schema..."
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f sql/001_create_tables.sql

echo ""
echo "✅ Database initialization complete!"
echo ""
echo "Tables created:"
psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "\dt quizplease.*"

echo ""
echo "==================================="
echo "Next steps:"
echo "1. Configure terraform/terraform.tfvars with these database credentials"
echo "2. Run ./deploy.sh to deploy the Lambda function"
echo "==================================="
