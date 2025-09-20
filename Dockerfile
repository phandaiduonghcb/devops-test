# Use the official Python image from the Docker Hub
FROM python:3.12-slim

# Set the working directory in the container
WORKDIR /app

# Copy the pyproject.toml file into the container
COPY pyproject.toml poetry.lock poetry.toml ./

# Install Poetry
RUN pip install --no-cache-dir poetry

# Install the dependencies using Poetry
RUN poetry install --no-root --no-interaction

# Copy the rest of the application code into the container
COPY . .

# Make run.sh executable
RUN chmod +x run.sh

# Expose the port the app runs on
EXPOSE 3000

# Use the run.sh script as the entrypoint
CMD ["./run.sh"]

