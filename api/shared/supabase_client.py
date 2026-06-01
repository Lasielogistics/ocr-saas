"""Per-customer database client - uses direct PostgreSQL."""
import json
import os
from pathlib import Path

from .db_client import DbClient, get_connection, close_connection


class SupabaseClientFactory:
    """Factory for creating per-customer database clients.

    For local PostgreSQL, all customers share the same database connection.
    """

    _clients: dict[str, DbClient] = {}
    _customer_configs: dict[str, dict] = {}

    @classmethod
    def load_customers_from_file(cls, config_path: str) -> None:
        """Load customer configurations from JSON file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Customer config file not found: {config_path}")

        with open(path, "r") as f:
            data = json.load(f)

        # For local PostgreSQL, use single connection
        db_url = os.getenv('DATABASE_URL', 'postgresql://tms:tms_secret_password@tms-postgres:5432/tms_main')
        db_client = DbClient(db_url)

        for customer_id, config_data in data.items():
            cls._customer_configs[customer_id] = config_data
            cls._clients[customer_id] = db_client

    @classmethod
    def get_client(cls, customer_id: str) -> DbClient:
        """Get database client for a customer."""
        if not cls._clients:
            # Auto-initialize if not done
            config_path = os.getenv("CUSTOMER_CONFIG_PATH", "/app/shared/customers.json")
            cls.load_customers_from_file(config_path)

        if customer_id not in cls._clients:
            # Return first available client
            if cls._clients:
                return list(cls._clients.values())[0]
            raise ValueError(f"No database client available")

        return cls._clients[customer_id]

    @classmethod
    def get_config(cls, customer_id: str) -> dict:
        """Get configuration for a customer."""
        if not cls._customer_configs:
            config_path = os.getenv("CUSTOMER_CONFIG_PATH", "/app/shared/customers.json")
            cls.load_customers_from_file(config_path)

        if customer_id not in cls._customer_configs:
            if cls._customer_configs:
                return list(cls._customer_configs.values())[0]
            raise ValueError(f"Unknown customer_id: {customer_id}")

        return cls._customer_configs[customer_id]

    @classmethod
    def add_customer(cls, config: dict) -> None:
        """Add a new customer."""
        customer_id = config.get('customer_id')
        cls._customer_configs[customer_id] = config
        db_url = os.getenv('DATABASE_URL', 'postgresql://tms:tms_secret_password@tms-postgres:5432/tms_main')
        cls._clients[customer_id] = DbClient(db_url)

    @classmethod
    def remove_customer(cls, customer_id: str) -> None:
        """Remove a customer."""
        cls._customer_configs.pop(customer_id, None)
        cls._clients.pop(customer_id, None)

    @classmethod
    def list_customers(cls) -> list[str]:
        """List all customer IDs."""
        return list(cls._customer_configs.keys())

    @classmethod
    def close_all(cls) -> None:
        """Close all connections."""
        close_connection()
        cls._clients.clear()


def get_supabase_client(customer_id: str = None) -> DbClient:
    """Convenience function to get a customer's database client."""
    return SupabaseClientFactory.get_client(customer_id)


def init_customer_clients() -> None:
    """Initialize customer clients from config file."""
    config_path = os.getenv("CUSTOMER_CONFIG_PATH", "/app/shared/customers.json")
    SupabaseClientFactory.load_customers_from_file(config_path)
