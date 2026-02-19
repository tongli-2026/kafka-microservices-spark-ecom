# Docker Images - Architecture Compatibility

## ARM64 (Apple Silicon) Native Images

All images in this project support ARM64 architecture natively:

| Service | Image | Architecture | Notes |
|---------|-------|--------------|-------|
| **Kafka Brokers** | `apache/kafka:latest` | Multi-arch (ARM64/AMD64) | Official Apache Kafka |
| **Spark Master** | `apache/spark:3.5.1` | Multi-arch (ARM64/AMD64) | Official Apache Spark |
| **Spark Workers** | `apache/spark:3.5.1` | Multi-arch (ARM64/AMD64) | Official Apache Spark |
| **PostgreSQL** | `postgres:15` | Multi-arch (ARM64/AMD64) | Official PostgreSQL |
| **Redis** | `redis:7-alpine` | Multi-arch (ARM64/AMD64) | Alpine-based, smaller image |
| **Kafka UI** | `provectuslabs/kafka-ui:latest` | Multi-arch (ARM64/AMD64) | Community-maintained |
| **Mailpit** | `axllent/mailpit:latest` | Multi-arch (ARM64/AMD64) | ✅ **ARM64-native** replacement for MailHog |

## Image Change Notes

### MailHog → Mailpit
- **Old**: `mailhog/mailhog` (AMD64 only - runs in emulation on Apple Silicon)
- **New**: `axllent/mailpit:latest` (ARM64-native)
- **Why**: Better performance on Apple Silicon, actively maintained
- **Compatibility**: Same SMTP port (1025) and Web UI port (8025)
- **Features**: Enhanced UI, better performance, modern codebase

## Verifying Architecture

To check if an image is running natively on your system:

```bash
# Check system architecture
uname -m  # Should show: arm64 (Apple Silicon) or x86_64 (Intel)

# Check image architecture
docker image inspect <image-name> --format '{{.Architecture}}'

# Check all images
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"

# Look for AMD64 warnings in Docker Desktop
docker ps  # Check for "AMD64" tags next to containers
```

## Performance Benefits (ARM64-native)

Running native ARM64 images provides:
- ✅ **Better Performance**: No x86-to-ARM translation overhead
- ✅ **Lower CPU Usage**: Native instruction execution
- ✅ **Reduced Battery Drain**: More efficient on MacBooks
- ✅ **Faster Startup**: No emulation layer

## All Services Architecture Status

```bash
✅ kafka-broker-1      arm64  (apache/kafka:latest)
✅ kafka-broker-2      arm64  (apache/kafka:latest)
✅ kafka-broker-3      arm64  (apache/kafka:latest)
✅ kafka-ui            arm64  (provectuslabs/kafka-ui:latest)
✅ spark-master        arm64  (apache/spark:3.5.1)
✅ spark-worker-1      arm64  (apache/spark:3.5.1)
✅ spark-worker-2      arm64  (apache/spark:3.5.1)
✅ postgres            arm64  (postgres:15)
✅ redis               arm64  (redis:7-alpine)
✅ mailhog             arm64  (axllent/mailpit:latest) - UPDATED!
✅ cart-service        arm64  (built from Python 3.11-slim)
✅ order-service       arm64  (built from Python 3.11-slim)
✅ payment-service     arm64  (built from Python 3.11-slim)
✅ inventory-service   arm64  (built from Python 3.11-slim)
✅ notification-service arm64  (built from Python 3.11-slim)
```

**Total: 15/15 containers running ARM64-native** 🎉
