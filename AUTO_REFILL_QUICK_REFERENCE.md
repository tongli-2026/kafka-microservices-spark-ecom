# Auto-Refill Inventory - Quick Reference

## Installation

```bash
pip install psycopg2-binary
```

## Quick Start

```bash
# Default settings (check every 10s, refill at <20 units, +50 units)
./scripts/auto-refill-inventory.py

# With load test in another terminal
./scripts/simulate-users.py --mode continuous --duration 600 --users 20
```

## Command Options

```bash
--threshold N           # Refill when stock < N (default: 20)
--refill-quantity N     # Add N units per refill (default: 50)
--interval N            # Check every N seconds (default: 10)
--verbose              # Debug logging
```

## Examples

```bash
# Light load (default)
./scripts/auto-refill-inventory.py

# Heavy stress test
./scripts/auto-refill-inventory.py --threshold 10 --refill-quantity 100

# Realistic inventory
./scripts/auto-refill-inventory.py --threshold 30 --refill-quantity 30 --interval 15

# Debug mode
./scripts/auto-refill-inventory.py --verbose
```

## Complete Workflow

```bash
# Terminal 1
docker-compose up -d && sleep 30

# Terminal 2
./scripts/spark/start-spark-jobs.sh

# Terminal 3
./scripts/auto-refill-inventory.py

# Terminal 4
./scripts/simulate-users.py --mode continuous --duration 600 --users 20
```

## Monitoring

```bash
# Check stock levels
docker-compose exec postgres psql -U postgres -d kafka_ecom \
  -c "SELECT product_id, name, stock FROM products ORDER BY stock LIMIT 10;"

# View refill logs
docker-compose logs | grep -i refill
```

## Stopping

Press `Ctrl+C` to stop - shows statistics:
- Duration
- Total refills
- Total units added
- Average refills per minute

## How It Works

1. Connects to PostgreSQL
2. Every N seconds: checks if any product stock < threshold
3. For low-stock products: `UPDATE stock = stock + refill_qty`
4. Logs activity with emoji indicators
5. On shutdown: prints summary statistics

## Full Documentation

See the script's docstring for complete documentation:

```bash
head -250 ./scripts/auto-refill-inventory.py
```

Or run with help:
```bash
python3 -c "import scripts.auto_refill_inventory as m; help(m)"
```
