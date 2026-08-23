"""One-time migration: fold learning_context_detail.contexts into
learning_context_detail.situations and drop the now-removed contexts field.

`contexts` duplicated the situations list with no Settings UI of its own —
it's how stray values (e.g. a junk "rest" entry) silently leaked into the
per-topic "Scoped User Memory" view with no way to see or remove them.

Run once, manually: python scripts/migrate_contexts_to_situations.py
"""

from pymongo import MongoClient

from app.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    client = MongoClient(settings.MONGODB_URI)
    db = client[settings.DATABASE_NAME]
    col = db["profiles"]

    migrated = 0
    for profile in col.find({"learning_context_detail.contexts": {"$exists": True}}):
        detail = dict(profile.get("learning_context_detail") or {})
        contexts = detail.pop("contexts", []) or []
        existing_situations = list(detail.get("situations") or [])

        existing_lower = {s.lower() for s in existing_situations}
        merged = existing_situations + [c for c in contexts if c.lower() not in existing_lower]
        detail["situations"] = merged[:20]

        col.update_one(
            {"_id": profile["_id"]},
            {"$set": {"learning_context_detail": detail}},
        )
        migrated += 1

    print(f"Migrated {migrated} profile(s).")


if __name__ == "__main__":
    main()
