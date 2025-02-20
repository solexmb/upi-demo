Test service-1 endpoint

curl -X POST http://localhost:8080/store -H "Content-Type: application/json" -d '{"value": "test data9"}'

curl -X GET http://localhost:8080/retrieve/1  