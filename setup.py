"""Setup configuration for kafka-microservices-spark-ecom project."""

from setuptools import setup, find_packages

setup(
    name="kafka-microservices-spark-ecom",
    version="1.0.0",
    description="Event-driven e-commerce backend with Kafka, FastAPI, and PySpark",
    author="Your Name",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "fastapi==0.109.0",
        "uvicorn==0.27.0",
        "redis==5.0.0",
        "confluent-kafka==2.3.0",
        "sqlalchemy==2.0.23",
        "alembic==1.13.1",
        "psycopg2-binary==2.9.9",
        "pydantic==2.5.0",
        "pydantic-settings==2.1.0",
        "pyspark==3.5.0",
    ],
)
