FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY service-1.py .

CMD ["python", "service-1.py"]