from typing import Optional, List, Dict, Any
from connectors.base import BaseConnector


class MongoDBConnector(BaseConnector):
    db_type = "mongodb"

    def __init__(self):
        self.client = None
        self.db = None
        self.database_name: str = ""

    def connect(self, **kwargs) -> Dict[str, Any]:
        try:
            from pymongo import MongoClient
        except ImportError:
            return {"status": "error", "message": "pymongo not installed. Run: pip install pymongo"}

        self.database_name = kwargs.get("database", "")
        if not self.database_name:
            return {"status": "error", "message": "Database name is required"}

        try:
            uri = kwargs.get("uri", "")
            if not uri:
                host = kwargs.get("host", "localhost")
                port = kwargs.get("port", 27017)
                user = kwargs.get("user", "")
                password = kwargs.get("password", "")
                if user and password:
                    uri = f"mongodb://{user}:{password}@{host}:{port}"
                else:
                    uri = f"mongodb://{host}:{port}"

            self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            self.client.server_info()
            self.db = self.client[self.database_name]
            return {"status": "connected", "database": self.database_name}
        except Exception as e:
            self.client = None
            self.db = None
            return {"status": "error", "message": str(e)}

    def disconnect(self):
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    @property
    def is_connected(self) -> bool:
        return self.client is not None and self.db is not None

    def get_tables(self) -> List[str]:
        return self.db.list_collection_names()

    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        collection = self.db[table_name]
        sample = list(collection.find().limit(10))

        field_types = {}
        for doc in sample:
            for key, value in doc.items():
                type_name = type(value).__name__
                if key not in field_types:
                    field_types[key] = set()
                field_types[key].add(type_name)

        columns = []
        for field, types in field_types.items():
            columns.append({
                "name": field,
                "type": ", ".join(types),
                "nullable": True,
                "default": None,
                "primary_key": field == "_id",
            })

        indexes = []
        for idx_name, idx_info in collection.index_information().items():
            indexes.append({
                "name": idx_name,
                "columns": [k for k, _ in idx_info["key"]],
                "unique": idx_info.get("unique", False),
            })

        return {
            "table": table_name,
            "columns": columns,
            "foreign_keys": [],
            "indexes": indexes,
        }

    def get_row_count(self, table_name: str) -> int:
        return self.db[table_name].estimated_document_count()

    def get_sample_data(self, table_name: str, limit: int = 3) -> List[Dict]:
        collection = self.db[table_name]
        docs = list(collection.find().limit(limit))
        return [{k: self._serialize(v) for k, v in doc.items()} for doc in docs]

    def execute_query(self, query: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Execute MongoDB operations via JSON command strings.

        Expects query as a JSON-like string:
        {"action": "find", "collection": "users", "filter": {"name": "John"}}
        """
        import json
        try:
            if isinstance(query, str):
                cmd = json.loads(query)
            else:
                cmd = query

            collection_name = cmd.get("collection", "")
            if not collection_name:
                return {"success": False, "error": "No collection specified"}

            collection = self.db[collection_name]
            action = cmd.get("action", "find")
            filter_query = cmd.get("filter", {})

            if action == "find":
                limit = cmd.get("limit", 100)
                projection = cmd.get("projection")
                sort = cmd.get("sort")
                cursor = collection.find(filter_query, projection)
                if sort:
                    cursor = cursor.sort(list(sort.items()))
                cursor = cursor.limit(limit)
                docs = [{k: self._serialize(v) for k, v in doc.items()} for doc in cursor]
                columns = list(docs[0].keys()) if docs else []
                return {"success": True, "columns": columns, "rows": docs, "row_count": len(docs)}

            elif action == "insert_one":
                doc = cmd.get("document", {})
                result = collection.insert_one(doc)
                return {"success": True, "affected_rows": 1, "inserted_id": str(result.inserted_id)}

            elif action == "update":
                update = cmd.get("update", {})
                result = collection.update_many(filter_query, update)
                return {"success": True, "affected_rows": result.modified_count}

            elif action == "delete":
                result = collection.delete_many(filter_query)
                return {"success": True, "affected_rows": result.deleted_count}

            elif action == "count":
                count = collection.count_documents(filter_query)
                return {"success": True, "rows": [{"count": count}], "row_count": 1, "columns": ["count"]}

            elif action == "aggregate":
                pipeline = cmd.get("pipeline", [])
                docs = [{k: self._serialize(v) for k, v in doc.items()} for doc in collection.aggregate(pipeline)]
                columns = list(docs[0].keys()) if docs else []
                return {"success": True, "columns": columns, "rows": docs, "row_count": len(docs)}

            else:
                return {"success": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"success": False, "error": str(e)}
