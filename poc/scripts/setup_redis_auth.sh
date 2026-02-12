#!/bin/bash
#
# Quick Redis Authentication Setup
# For development/testing environments
#

set -e

echo "======================================"
echo "Redis Authentication Setup"
echo "======================================"

# Generate strong password
REDIS_PASSWORD=$(openssl rand -base64 32)
echo "Generated password: $REDIS_PASSWORD"

# Detect OS and Redis config location
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS (Homebrew)
    REDIS_CONF="/opt/homebrew/etc/redis.conf"
    REDIS_SERVICE="brew services restart redis"
elif [[ -f "/etc/redis/redis.conf" ]]; then
    # Linux (most distributions)
    REDIS_CONF="/etc/redis/redis.conf"
    REDIS_SERVICE="sudo systemctl restart redis"
elif [[ -f "/etc/redis.conf" ]]; then
    # Alternative Redis location
    REDIS_CONF="/etc/redis.conf"
    REDIS_SERVICE="sudo systemctl restart redis"
else
    echo "Error: Could not find redis.conf"
    echo "Please manually configure Redis authentication"
    exit 1
fi

echo "Found Redis config: $REDIS_CONF"

# Backup original config
if [[ ! -f "$REDIS_CONF.backup" ]]; then
    echo "Creating backup: $REDIS_CONF.backup"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        cp "$REDIS_CONF" "$REDIS_CONF.backup"
    else
        sudo cp "$REDIS_CONF" "$REDIS_CONF.backup"
    fi
fi

# Add authentication
echo ""
echo "Adding authentication to Redis config..."

if grep -q "^requirepass" "$REDIS_CONF"; then
    echo "Warning: requirepass already set in config"
    echo "Updating existing password..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/^requirepass.*/requirepass $REDIS_PASSWORD/" "$REDIS_CONF"
    else
        sudo sed -i "s/^requirepass.*/requirepass $REDIS_PASSWORD/" "$REDIS_CONF"
    fi
else
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "requirepass $REDIS_PASSWORD" >> "$REDIS_CONF"
    else
        echo "requirepass $REDIS_PASSWORD" | sudo tee -a "$REDIS_CONF" > /dev/null
    fi
fi

# Bind to localhost for security
if ! grep -q "^bind 127.0.0.1" "$REDIS_CONF"; then
    echo "Binding Redis to localhost..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "bind 127.0.0.1 ::1" >> "$REDIS_CONF"
    else
        echo "bind 127.0.0.1 ::1" | sudo tee -a "$REDIS_CONF" > /dev/null
    fi
fi

# Restart Redis
echo ""
echo "Restarting Redis..."
eval $REDIS_SERVICE

sleep 2

# Test connection
echo ""
echo "Testing Redis authentication..."
if redis-cli -a "$REDIS_PASSWORD" ping > /dev/null 2>&1; then
    echo "✅ Redis authentication working!"
else
    echo "❌ Redis authentication test failed"
    exit 1
fi

# Save password to .env
echo ""
echo "Saving password to .env file..."
if [[ -f ".env" ]]; then
    # Update existing .env
    if grep -q "^REDIS_PASSWORD=" ".env"; then
        sed -i.bak "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$REDIS_PASSWORD/" .env
    else
        echo "REDIS_PASSWORD=$REDIS_PASSWORD" >> .env
    fi
else
    # Create new .env
    echo "REDIS_PASSWORD=$REDIS_PASSWORD" > .env
fi

echo "✅ Password saved to .env"

echo ""
echo "======================================"
echo "Setup Complete!"
echo "======================================"
echo ""
echo "Redis is now secured with authentication."
echo "Password has been saved to .env file."
echo ""
echo "To use Redis manually:"
echo "  redis-cli -a \$REDIS_PASSWORD ping"
echo ""
echo "Workers will automatically use the password from .env"
echo ""
