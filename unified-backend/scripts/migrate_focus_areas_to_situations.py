"""One-time migration: fold profiles.focus_areas into learning_context_detail.situations
and drop the now-removed focus_areas field.

Run once, manually: python scripts/migrate_focus_areas_to_situations.py
"""

from pymongo import MongoClient

from app.config.settings import get_settings


def main() -> None:
    settings = get_settings()
    client = MongoClient(settings.MONGODB_URI)
    db = client[settings.DATABASE_NAME]
    col = db["profiles"]

    migrated = 0
    for profile in col.find({"focus_areas": {"$exists": True}}):
        focus_areas = profile.get("focus_areas") or []
        detail = dict(profile.get("learning_context_detail") or {})
        existing_situations = list(detail.get("situations") or [])

        existing_lower = {s.lower() for s in existing_situations}
        merged = existing_situations + [a for a in focus_areas if a.lower() not in existing_lower]

        detail["learning_context"] = (
            detail.get("learning_context") or profile.get("learning_context") or "self_directed"
        )
        detail["situations"] = merged[:20]

        update: dict = {"$set": {"learning_context_detail": detail}, "$unset": {"focus_areas": ""}}
        col.update_one({"_id": profile["_id"]}, update)
        migrated += 1

    print(f"Migrated {migrated} profile(s).")


if __name__ == "__main__":
    main()
