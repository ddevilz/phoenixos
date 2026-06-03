#!/usr/bin/env python
"""Seed 3 synthetic SUPPRESSED_BY fix chains for hackathon demo.

Chain A (depth 3): fix-a1 -> fix-a2 -> fix-a3 -> fix-a4 (root)
Chain B (depth 2): fix-b1 -> fix-b2 -> fix-b3 (root)
Chain C (depth 1): fix-c1 -> fix-c2 (root)

Run: NEO4J_URI=bolt://localhost:7687 NEO4J_AUTH=neo4j/phoenixos python scripts/seed_fixes.py
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone

from neo4j import AsyncGraphDatabase


async def seed() -> None:
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    auth_str = os.environ.get("NEO4J_AUTH", "neo4j/phoenixos")
    user, password = auth_str.split("/", 1)

    async with AsyncGraphDatabase.driver(uri, auth=(user, password)) as driver:
        async with driver.session() as session:
            now = datetime.now(timezone.utc)

            fixes = [
                # Chain A: depth 3
                {"id": "fix-a1", "commit_sha": "aa111", "author_type": "ai",
                 "description": "Patch A1: suppress symptom",
                 "timestamp": (now - timedelta(days=1)).isoformat(), "suppressed_by": "fix-a2"},
                {"id": "fix-a2", "commit_sha": "aa222", "author_type": "human",
                 "description": "Patch A2: another workaround",
                 "timestamp": (now - timedelta(days=8)).isoformat(), "suppressed_by": "fix-a3"},
                {"id": "fix-a3", "commit_sha": "aa333", "author_type": "ai",
                 "description": "Patch A3: temp fix",
                 "timestamp": (now - timedelta(days=15)).isoformat(), "suppressed_by": "fix-a4"},
                {"id": "fix-a4", "commit_sha": "aa444", "author_type": "human",
                 "description": "Root cause A",
                 "timestamp": (now - timedelta(days=22)).isoformat(), "suppressed_by": None},
                # Chain B: depth 2
                {"id": "fix-b1", "commit_sha": "bb111", "author_type": "ai",
                 "description": "Patch B1: surface fix",
                 "timestamp": (now - timedelta(days=2)).isoformat(), "suppressed_by": "fix-b2"},
                {"id": "fix-b2", "commit_sha": "bb222", "author_type": "human",
                 "description": "Patch B2: deeper fix",
                 "timestamp": (now - timedelta(days=9)).isoformat(), "suppressed_by": "fix-b3"},
                {"id": "fix-b3", "commit_sha": "bb333", "author_type": "human",
                 "description": "Root cause B",
                 "timestamp": (now - timedelta(days=16)).isoformat(), "suppressed_by": None},
                # Chain C: depth 1
                {"id": "fix-c1", "commit_sha": "cc111", "author_type": "ai",
                 "description": "Patch C1: quick fix",
                 "timestamp": (now - timedelta(days=3)).isoformat(), "suppressed_by": "fix-c2"},
                {"id": "fix-c2", "commit_sha": "cc222", "author_type": "human",
                 "description": "Root cause C",
                 "timestamp": (now - timedelta(days=10)).isoformat(), "suppressed_by": None},
            ]

            await session.run(
                """
                UNWIND $fixes AS f
                MERGE (n:Fix {id: f.id})
                SET n.commit_sha = f.commit_sha,
                    n.author_type = f.author_type,
                    n.description = f.description,
                    n.timestamp = f.timestamp
                """,
                fixes=fixes,
            )

            edges = [f for f in fixes if f["suppressed_by"] is not None]
            await session.run(
                """
                UNWIND $edges AS e
                MATCH (a:Fix {id: e.id}), (b:Fix {id: e.suppressed_by})
                MERGE (a)-[:SUPPRESSED_BY]->(b)
                """,
                edges=edges,
            )

            print(f"Seeded {len(fixes)} Fix nodes and {len(edges)} SUPPRESSED_BY edges.")


if __name__ == "__main__":
    asyncio.run(seed())
