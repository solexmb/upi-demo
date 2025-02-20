# from flask import Flask, request, jsonify
# import psycopg2
# import os

# app = Flask(__name__)

# # YugabyteDB connection details
# DB_HOST = os.getenv("DB_HOST", "yugabyte-tserver")
# DB_PORT = os.getenv("DB_PORT", "5433")
# DB_NAME = os.getenv("DB_NAME", "yugabyte")
# DB_USER = os.getenv("DB_USER", "yugabyte")
# DB_PASSWORD = os.getenv("DB_PASSWORD", "yugabyte")

# # Connect to YugabyteDB
# def get_db_connection():
#     return psycopg2.connect(
#         host=DB_HOST,
#         port=DB_PORT,
#         dbname=DB_NAME,
#         user=DB_USER,
#         password=DB_PASSWORD
#     )

# # Dapr configuration endpoint
# @app.route('/dapr/config', methods=['GET'])
# def dapr_config():
#     return jsonify({}), 200

# # Dapr subscription endpoint
# @app.route('/dapr/subscribe', methods=['GET'])
# def dapr_subscribe():
#     subscriptions = [
#         {
#             "pubsubname": "kafka-pubsub",
#             "topic": "messages",
#             "route": "/process"
#         }
#     ]
#     return jsonify(subscriptions), 200

# # Endpoint to process messages from Kafka
# @app.route('/process', methods=['POST'])
# def process_message():
#     message = request.json
#     print(f"Received message: {message}")

#     # Store the message in YugabyteDB
#     conn = get_db_connection()
#     cur = conn.cursor()
#     cur.execute("INSERT INTO processed_data (id, value) VALUES (%s, %s)", (message['id'], message['value']))
#     conn.commit()
#     cur.close()
#     conn.close()

#     return jsonify({"status": "processed"}), 200

# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5001)




# from flask import Flask, request, jsonify
# import psycopg2
# import os

# app = Flask(__name__)

# # YugabyteDB connection details
# DB_HOST = os.getenv("DB_HOST", "yugabyte-tserver")
# DB_PORT = os.getenv("DB_PORT", "5433")
# DB_NAME = os.getenv("DB_NAME", "yugabyte")
# DB_USER = os.getenv("DB_USER", "yugabyte")
# DB_PASSWORD = os.getenv("DB_PASSWORD", "yugabyte")

# # Connect to YugabyteDB
# def get_db_connection():
#     return psycopg2.connect(
#         host=DB_HOST,
#         port=DB_PORT,
#         dbname=DB_NAME,
#         user=DB_USER,
#         password=DB_PASSWORD
#     )

# # Dapr configuration endpoint
# @app.route('/dapr/config', methods=['GET'])
# def dapr_config():
#     return jsonify({}), 200

# # Dapr subscription endpoint
# @app.route('/dapr/subscribe', methods=['GET'])
# def dapr_subscribe():
#     subscriptions = [
#         {
#             "pubsubname": "kafka-pubsub",
#             "topic": "messages",
#             "route": "/process"
#         }
#     ]
#     return jsonify(subscriptions), 200

# # Endpoint to process messages from Kafka
# @app.route('/process', methods=['POST'])
# def process_message():
#     message = request.json
#     print(f"Received message: {message}")

#     # Store the message in YugabyteDB
#     conn = get_db_connection()
#     cur = conn.cursor()
    
#     try:
#         # Insert or update the record if it exists
#         cur.execute("""
#             INSERT INTO processed_data (id, value)
#             VALUES (%s, %s)
#             ON CONFLICT (id)
#             DO UPDATE SET value = EXCLUDED.value;
#         """, (message['id'], message['value']))
        
#         conn.commit()
#         print(f"Processed message: id={message['id']}, value={message['value']}")
#     except Exception as e:
#         print(f"Database Error: {str(e)}")
#         conn.rollback()  # Rollback the transaction in case of error
#     finally:
#         cur.close()
#         conn.close()

#     return jsonify({"status": "processed"}), 200

# if __name__ == '__main__':
#     app.run(host='0.0.0.0', port=5001)






from flask import Flask, request, jsonify
import psycopg2
import os

app = Flask(__name__)

# YugabyteDB connection details
DB_HOST = os.getenv("DB_HOST", "yugabyte-tserver")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "yugabyte")
DB_USER = os.getenv("DB_USER", "yugabyte")
DB_PASSWORD = os.getenv("DB_PASSWORD", "yugabyte")

# Connect to YugabyteDB
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# Dapr configuration endpoint
@app.route('/dapr/config', methods=['GET'])
def dapr_config():
    return jsonify({}), 200

# Dapr subscription endpoint
@app.route('/dapr/subscribe', methods=['GET'])
def dapr_subscribe():
    subscriptions = [
        {
            "pubsubname": "kafka-pubsub",
            "topic": "messages",
            "route": "/process"
        }
    ]
    return jsonify(subscriptions), 200

# Endpoint to process messages from Kafka
@app.route('/process', methods=['POST'])
def process_message():
    message = request.json
    print(f"Received message: {message}")

    # Store the message in YugabyteDB
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Extract 'id' and 'value' from the 'data' field
        message_data = message.get('data', {})
        message_id = message_data.get('id')
        message_value = message_data.get('value')

        if not message_id or not message_value:
            print("Invalid message: Missing 'id' or 'value'")
            return jsonify({"error": "Missing 'id' or 'value' in message"}), 400

        # Insert or update the record if it exists
        cur.execute("""
            INSERT INTO processed_data (id, value)
            VALUES (%s, %s)
            ON CONFLICT (id)
            DO UPDATE SET value = EXCLUDED.value;
        """, (message_id, message_value))
        
        conn.commit()
        print(f"Processed message: id={message_id}, value={message_value}")
    except Exception as e:
        print(f"Database Error: {str(e)}")
        conn.rollback()  # Rollback the transaction in case of error
    finally:
        cur.close()
        conn.close()

    return jsonify({"status": "processed"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)

