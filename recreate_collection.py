#!/usr/bin/env python3
"""
Delete and recreate the avoca-next collection to start fresh with the fixed code.
"""

import sys
from pathlib import Path

from qdrant_client import QdrantClient

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from claude_indexer.config.config_loader import ConfigLoader


def recreate_collection():
    """Delete and prepare collection for fresh indexing"""
    print("\n" + "=" * 60)
    print("🔄 RECREATING AVOCA-NEXT COLLECTION")
    print("=" * 60)

    # Load configuration
    config = ConfigLoader().load()

    # Initialize direct client
    client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)

    collection_name = "avoca-next"

    try:
        # Step 1: Delete existing collection if it exists
        print(f"\n🗑️ Deleting existing collection: {collection_name}")
        try:
            client.delete_collection(collection_name)
            print(f"  ✅ Successfully deleted collection: {collection_name}")
        except Exception as e:
            print(f"  ℹ️ Collection doesn't exist or already deleted: {e}")

        # Step 2: Verify deletion
        try:
            collections = client.get_collections()
            collection_names = [c.name for c in collections.collections]
            if collection_name not in collection_names:
                print(f"  ✅ Confirmed: Collection {collection_name} has been removed")
            else:
                print(f"  ⚠️ Warning: Collection {collection_name} still exists")
                return False
        except Exception as e:
            print(f"  ❌ Error checking collections: {e}")
            return False

        print("\n" + "=" * 60)
        print("✅ COLLECTION DELETED SUCCESSFULLY!")
        print("The avoca-next collection has been completely removed.")
        print("The indexer will create a fresh collection on next run.")
        print("=" * 60)

        return True

    except Exception as e:
        print(f"\n❌ Failed to recreate collection: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = recreate_collection()
    sys.exit(0 if success else 1)
