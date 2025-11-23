# Use Python 3.13 slim image for smaller size
FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install Python dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY bot.py ./
COPY src/ ./src/

# Create non-root user for security
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

# Run the bot
CMD ["uv", "run", "bot.py"]
