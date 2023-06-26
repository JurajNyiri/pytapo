FROM tiangolo/uvicorn-gunicorn-fastapi:python3.10

ARG PYTHONUNBUFFERED=1
ENV PORT=8080
ENV HOST=0.0.0.0

# Stage 1 - Build

# Install poetry
RUN pip install poetry

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install dependencies
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi

# Expose the port
EXPOSE $PORT

# Run the app
CMD ["poetry", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]