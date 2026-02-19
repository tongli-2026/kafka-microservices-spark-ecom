# Port Mapping Reference

## All Ports Used in This Project

### Kafka Brokers
| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| kafka-broker-1 | 9092 | 9092 | Kafka internal |
| kafka-broker-1 | 9094 | 9094 | Kafka external |
| kafka-broker-2 | 9093 | 9092 | Kafka internal |
| kafka-broker-2 | 9095 | 9094 | Kafka external |
| kafka-broker-3 | 9091 | 9092 | Kafka internal |
| kafka-broker-3 | 9096 | 9094 | Kafka external |

### Kafka UI
| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| kafka-ui | 8080 | 8080 | Web UI for Kafka management |

### Spark Cluster
| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| spark-master | **9080** | 8080 | Spark Master Web UI |
| spark-master | 7077 | 7077 | Spark Master communication |
| spark-worker-1 | 8081 | 8081 | Worker 1 Web UI |
| spark-worker-1 | 4040 | 4040 | Spark Driver Web UI |
| spark-worker-2 | 8082 | 8081 | Worker 2 Web UI |

### Database & Cache
| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| postgres | 5432 | 5432 | PostgreSQL database |
| redis | 6379 | 6379 | Redis cache |

### Email
| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| mailhog | 1025 | 1025 | SMTP server |
| mailhog | 8025 | 8025 | Mailpit Web UI (ARM64-native) |

### Microservices
| Service | Host Port | Container Port | Purpose |
|---------|-----------|----------------|---------|
| cart-service | 8001 | 8001 | Cart REST API |
| order-service | 8002 | 8002 | Order REST API |
| payment-service | 8003 | 8003 | Payment REST API |
| inventory-service | 8004 | 8004 | Inventory REST API |
| notification-service | 8005 | 8005 | Notification REST API |

## Quick Access URLs

### Management UIs
- **Kafka UI**: http://localhost:8080
- **Spark Master UI**: http://localhost:9080 ⚡ **(Changed to avoid conflict)**
- **Spark Worker 1 UI**: http://localhost:8081
- **Spark Worker 2 UI**: http://localhost:8082
- **Spark Driver UI**: http://localhost:4040 (when job is running)
- **MailHog UI**: http://localhost:8025

### Microservices APIs
- **Cart Service**: http://localhost:8001/docs
- **Order Service**: http://localhost:8002/docs
- **Payment Service**: http://localhost:8003/docs
- **Inventory Service**: http://localhost:8004/docs
- **Notification Service**: http://localhost:8005/docs

### Database Connections
- **PostgreSQL**: localhost:5432 (user: postgres, password: postgres, db: kafka_ecom)
- **Redis**: localhost:6379

## Port Conflict Resolution

✅ **Fixed Conflict**: Spark Master UI moved from 8080 → 9080 to avoid conflict with Kafka UI

## Total Ports Used: 21

All ports are checked and verified to be unique!
