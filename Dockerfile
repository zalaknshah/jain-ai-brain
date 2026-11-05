FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-cache-dir .

ENV JACE_HOST=0.0.0.0
ENV JACE_PORT=8787
EXPOSE 8787
CMD ["python", "-m", "jace.cli", "serve"]
