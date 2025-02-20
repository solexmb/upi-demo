# FROM python:3.9-slim

# WORKDIR /app
# COPY requirements.txt .
# RUN pip install -r requirements.txt

# COPY service-2.py .

# CMD ["python", "service-2.py"]


# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install Dapr Python SDK (if not in requirements.txt)
RUN pip install dapr==1.8.0

# Make port 5001 available to the world outside this container
EXPOSE 5001

# Define environment variable
ENV NAME World

# Run service-2.py when the container launches
CMD ["python", "service-2.py"]
