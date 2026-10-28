"""Where the app keeps what admins change: local files or MongoDB.

Stored items: the admin PIN hash and confirmed column mapping ("config"),
the phases with their name corrections ("phases"), and uploaded master lists.

- Local files (default): config.json, phases.json and masters/ next to app.py.
- MongoDB: used when the MONGODB_URI setting is present, for hosts such as
  Streamlit Community Cloud that wipe local files on restart. MONGODB_DB
  picks the database (default "nrbc_dashboard").

The public demo (DEMO_MODE) always uses local files and never connects to a
database, even if MONGODB_URI is set, so it can never touch live data.
"""

import functools
import json
from pathlib import Path

from reporting.infrastructure.settings import get_flag, get_setting

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = "nrbc_dashboard"


class StorageError(RuntimeError):
    """Saved settings could not be read or written."""


class FileStore:
    """JSON documents and files in the project folder."""

    def __init__(self, root=None):
        self.root = Path(root or PROJECT_ROOT)

    def describe(self) -> str:
        return "local files"

    def _json_path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def load_json(self, key: str):
        path = self._json_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise StorageError(f"Could not read {path.name}.") from exc

    def save_json(self, key: str, data) -> None:
        try:
            self._json_path(key).write_text(json.dumps(data, indent=1), encoding="utf-8")
        except OSError as exc:
            raise StorageError(f"Could not save {key}.json.") from exc

    def load_file(self, name: str):
        path = self.root / name
        try:
            return path.read_bytes() if path.is_file() else None
        except OSError as exc:
            raise StorageError(f"Could not read {name}.") from exc

    def save_file(self, name: str, data: bytes) -> None:
        path = self.root / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError as exc:
            raise StorageError(f"Could not save {name}.") from exc

    def delete_file(self, name: str) -> None:
        try:
            (self.root / name).unlink(missing_ok=True)
        except OSError:
            pass


@functools.lru_cache(maxsize=4)
def _client(uri: str):
    if uri.startswith("mongomock://"):
        import mongomock  # local testing without a server

        return mongomock.MongoClient()
    from pymongo import MongoClient

    return MongoClient(uri, serverSelectionTimeoutMS=8000)


class MongoStore:
    """The same documents and files in MongoDB.

    Documents are kept as JSON text, because zone, center and column names
    may contain characters MongoDB doesn't allow in field names.
    """

    def __init__(self, uri: str, db_name: str = DEFAULT_DB):
        self.db = _client(uri)[db_name]

    def describe(self) -> str:
        return "MongoDB"

    @staticmethod
    def _call(action: str, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(
                f"Could not {action} the database. Check MONGODB_URI and that this "
                "host's IP address is allowed in MongoDB Atlas (Network Access)."
            ) from exc

    def load_json(self, key: str):
        doc = self._call("read from", self.db.settings.find_one, {"_id": key})
        return json.loads(doc["json"]) if doc else None

    def save_json(self, key: str, data) -> None:
        self._call("save to", self.db.settings.replace_one,
                   {"_id": key}, {"_id": key, "json": json.dumps(data)}, upsert=True)

    def load_file(self, name: str):
        doc = self._call("read from", self.db.files.find_one, {"_id": name})
        return bytes(doc["data"]) if doc else None

    def save_file(self, name: str, data: bytes) -> None:
        self._call("save to", self.db.files.replace_one,
                   {"_id": name}, {"_id": name, "data": data}, upsert=True)

    def delete_file(self, name: str) -> None:
        self._call("save to", self.db.files.delete_one, {"_id": name})


def get_store():
    """MongoDB when MONGODB_URI is set (never in the demo), else local files."""
    if not get_flag("DEMO_MODE"):
        uri = get_setting("MONGODB_URI")
        if uri:
            return MongoStore(str(uri), str(get_setting("MONGODB_DB", DEFAULT_DB)))
    return FileStore()
