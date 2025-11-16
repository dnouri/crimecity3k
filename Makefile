# CrimeCity3K Makefile

# Configuration
CONFIG := config.toml

# Directories
DATA_DIR := data
H3_DIR := $(DATA_DIR)/h3
TILES_DIR := $(DATA_DIR)/tiles

# Code dependencies (SQL files trigger rebuilds)
SQL_DIR := crimecity3k/sql

# Phony targets
.PHONY: install check test clean help

# Default target
help:
	@echo "CrimeCity3K - Available targets:"
	@echo "  install      - Install dependencies with uv"
	@echo "  check        - Run linting and type checking"
	@echo "  test         - Run test suite with coverage"
	@echo "  clean        - Remove generated files and caches"

install:
	uv sync --all-extras

check:
	uv run ruff check crimecity3k tests
	uv run ruff format --check crimecity3k tests
	uv run mypy crimecity3k tests

test:
	uv run pytest tests/ -v -n auto --cov=crimecity3k --cov-report=html --cov-report=term

clean:
	rm -rf $(H3_DIR) $(TILES_DIR)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.tmp" -delete
	rm -rf .mypy_cache .ruff_cache htmlcov .coverage
