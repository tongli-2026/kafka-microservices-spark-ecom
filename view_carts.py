import redis
import json

try:
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    # Sends a PING command to the Redis server to check if it's alive and reachable. 
    # If the server responds with PONG, it means the connection is successful.
    redis_client.ping()
except Exception as e:
    print(f"❌ Failed to connect to Redis: {e}")
    print("Make sure Redis is running: docker-compose up redis -d")
    exit(1)

try:
    cart_keys = redis_client.keys("cart:*")
    print(f"✅ Found {len(cart_keys)} active carts:\n")

    if len(cart_keys) == 0:
        print("No carts found. Add items via the API first, e.g.:")
        print("\ncurl -X POST http://localhost:8001/cart/user123/items \\")
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"product_id": "laptop", "quantity": 1, "price": 999.99}\'\n')
    else:
        for key in cart_keys:
            cart_data = redis_client.get(key)
            user_id = key.replace("cart:", "")
            ttl = redis_client.ttl(key)
            
            print(f"👤 User: {user_id}")
            print(f"⏱️  TTL: {ttl} seconds remaining")
            print(f"🛒 Items: {json.dumps(json.loads(cart_data), indent=2)}")
            print("-" * 50)
            
except Exception as e:
    print(f"❌ Error: {e}")
    exit(1)