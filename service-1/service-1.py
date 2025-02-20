# from flask import Flask, request, jsonify
# import psycopg2
# import requests
# import os

# app = Flask(__name__)

# # YugabyteDB connection details
# DB_HOST = os.getenv("DB_HOST", "yb-tserver-service.yugabyte.svc.cluster.local")
# DB_PORT = os.getenv("DB_PORT", "5433")
# DB_NAME = os.getenv("DB_NAME", "yugabyte")
# DB_USER = os.getenv("DB_USER", "yugabyte")
# DB_PASSWORD = os.getenv("DB_PASSWORD", "yugabyte")

# # Dapr sidecar URL
# DAPR_URL = os.getenv("DAPR_URL", "http://localhost:3500")

# # Connect to YugabyteDB
# def get_db_connection():
#     return psycopg2.connect(
#         host=DB_HOST,
#         port=DB_PORT,
#         dbname=DB_NAME,
#         user=DB_USER,
#         password=DB_PASSWORD
#     )

# # Create a table if it doesn't exist
# def initialize_db():
#     conn = get_db_connection()
#     cur = conn.cursor()
#     cur.execute("""
#         CREATE TABLE IF NOT EXISTS data (
#             id SERIAL PRIMARY KEY,
#             value TEXT NOT NULL
#         )
#     """)
#     conn.commit()
#     cur.close()
#     conn.close()

# # Endpoint to store data in YugabyteDB
# @app.route('/store', methods=['POST'])
# def store_data():
#     data = request.json.get('value')
#     conn = get_db_connection()
#     cur = conn.cursor()
#     cur.execute("INSERT INTO data (value) VALUES (%s) RETURNING id", (data,))
#     row_id = cur.fetchone()[0]
#     conn.commit()
#     cur.close()
#     conn.close()

#     # Publish a message to Kafka via Dapr Pub/Sub
#     message = {"id": row_id, "value": data}
#     requests.post(f"{DAPR_URL}/v1.0/publish/kafka-pubsub/messages", json=message)

#     return jsonify({"id": row_id, "value": data}), 201

# # Endpoint to retrieve data from YugabyteDB
# @app.route('/retrieve/<int:id>', methods=['GET'])
# def retrieve_data(id):
#     conn = get_db_connection()
#     cur = conn.cursor()
#     cur.execute("SELECT value FROM data WHERE id = %s", (id,))
#     result = cur.fetchone()
#     cur.close()
#     conn.close()

#     if result:
#         return jsonify({"id": id, "value": result[0]}), 200
#     else:
#         return jsonify({"error": "Data not found"}), 404

# if __name__ == '__main__':
#     initialize_db()
#     app.run(host='0.0.0.0', port=5000)


from flask import Flask, request, jsonify
import psycopg2
import requests
import os
import logging

app = Flask(__name__)

# Enable logging
logging.basicConfig(level=logging.INFO)

# YugabyteDB connection details
DB_HOST = os.getenv("DB_HOST", "yb-tserver-service.yugabyte.svc.cluster.local")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "yugabyte")
DB_USER = os.getenv("DB_USER", "yugabyte")
DB_PASSWORD = os.getenv("DB_PASSWORD", "yugabyte")

# Dapr sidecar URL
DAPR_URL = os.getenv("DAPR_URL", "http://localhost:3500")

# Connect to YugabyteDB
def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

# Create a table if it doesn't exist
def initialize_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS data (
            id SERIAL PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# Endpoint to store data in YugabyteDB
@app.route('/store', methods=['POST'])
def store_data():
    data = request.json.get('value')
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO data (value) VALUES (%s) RETURNING id", (data,))
    row_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    # Log the data being published to Kafka
    message = {"id": row_id, "value": data}
    logging.info(f"Publishing message to Kafka: {message}")

    # Publish the message to Kafka via Dapr Pub/Sub
    response = requests.post(f"{DAPR_URL}/v1.0/publish/kafka-pubsub/messages", json=message)
    logging.info(f"Response from Kafka publish: {response.status_code} - {response.text}")

    return jsonify({"id": row_id, "value": data}), 201

# Endpoint to retrieve data from YugabyteDB
@app.route('/retrieve/<int:id>', methods=['GET'])
def retrieve_data(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM data WHERE id = %s", (id,))
    result = cur.fetchone()
    cur.close()
    conn.close()

    if result:
        return jsonify({"id": id, "value": result[0]}), 200
    else:
        return jsonify({"error": "Data not found"}), 404

if __name__ == '__main__':
    initialize_db()
    app.run(host='0.0.0.0', port=5000)
