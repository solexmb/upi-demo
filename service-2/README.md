Test service-2 endpoint

curl -X POST http://localhost:5001/process \
  -H "Content-Type: application/json" \
  -d '{"data": {"id": "abc123", "value": "test event"}}'
