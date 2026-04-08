"""Per-customer Supabase client factory."""
import json
import os
from pathlib import Path
from typing import Optional

from supabase import create_client, Client

from .models import CustomerConfig


class SupabaseClientFactory:
    """Factory for creating per-customer Supabase clients."""

    _clients: dict[str, Client] = {}
    _customer_configs: dict[str, CustomerConfig] = {}

    @classmethod
    def load_customers_from_file(cls, config_path: str) -> None:
        """Load customer configurations from JSON file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Customer config file not found: {config_path}")

        with open(path, "r") as f:
            data = json.load(f)

        for customer_id, config_data in data.items():
            config = CustomerConfig(customer_id=customer_id, **config_data)
            cls._customer_configs[customer_id] = config
            cls._clients[customer_id] = create_client(
                config.supabase_url,
                config.supabase_key
            )

    @classmethod
    def get_client(cls, customer_id: str) -> Client:
        """Get Supabase client for a customer."""
        if customer_id not in cls._clients:
            raise ValueError(f"Unknown customer_id: {customer_id}")
        return cls._clients[customer_id]

    @classmethod
    def get_config(cls, customer_id: str) -> CustomerConfig:
        """Get configuration for a customer."""
        if customer_id not in cls._customer_configs:
            raise ValueError(f"Unknown customer_id: {customer_id}")
        return cls._customer_configs[customer_id]

    @classmethod
    def add_customer(cls, config: CustomerConfig) -> None:
        """Add a new customer and create their Supabase client."""
        cls._customer_configs[config.customer_id] = config
        cls._clients[config.customer_id] = create_client(
            config.supabase_url,
            config.supabase_key
        )

    @classmethod
    def remove_customer(cls, customer_id: str) -> None:
        """Remove a customer."""
        cls._customer_configs.pop(customer_id, None)
        cls._clients.pop(customer_id, None)

    @classmethod
    def list_customers(cls) -> list[str]:
        """List all customer IDs."""
        return list(cls._customer_configs.keys())


def get_supabase_client(customer_id: str) -> Client:
    """Convenience function to get a customer's Supabase client."""
    return SupabaseClientFactory.get_client(customer_id)


def init_customer_clients() -> None:
    """Initialize customer clients from config file."""
    config_path = os.getenv("CUSTOMER_CONFIG_PATH", "/app/shared/customers.json")
    SupabaseClientFactory.load_customers_from_file(config_path)
