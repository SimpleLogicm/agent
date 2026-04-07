from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any


class BaseConnector(ABC):
    """Abstract base class for all database connectors."""

    db_type: str = "unknown"

    @abstractmethod
    def connect(self, **kwargs) -> Dict[str, Any]:
        """Connect to the database. Returns status dict."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect from the database."""
        pass

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @abstractmethod
    def get_tables(self) -> List[str]:
        """Return list of table/collection names."""
        pass

    @abstractmethod
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """Return schema info for a single table/collection."""
        pass

    @abstractmethod
    def get_row_count(self, table_name: str) -> int:
        """Return number of rows/documents in a table/collection."""
        pass

    @abstractmethod
    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict]:
        """Return sample rows/documents from a table/collection."""
        pass

    @abstractmethod
    def execute_query(self, query: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute a query/command and return results."""
        pass

    def get_full_schema(self) -> Dict[str, Any]:
        """Return full schema for all tables/collections."""
        tables = self.get_tables()
        schema = {}
        for table in tables:
            schema[table] = self.get_table_schema(table)
            try:
                schema[table]["row_count"] = self.get_row_count(table)
            except Exception:
                schema[table]["row_count"] = -1
        return schema

    @staticmethod
    def _serialize(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (int, float, str, bool)):
            return value
        return str(value)
