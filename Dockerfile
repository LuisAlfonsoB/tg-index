# Use an official Python runtime as a parent image
FROM python:3.8

# Set environment variable to ensure Python output is sent straight to terminal without buffering
ENV PYTHONUNBUFFERED 1

# Set working directory to /tgindex
WORKDIR /tgindex

# Copy only the requirements file, to take advantage of Docker cache
COPY requirements.txt /tgindex/

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /tgindex
COPY . /tgindex/

cmd ["python", "app"]
