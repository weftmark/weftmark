"""
Generate a JSON schema document and Mermaid ER diagram from the live PostgreSQL database.

Usage:
    python scripts/db_schema.py [--env .env.dev] [--out docs/schema]

Outputs:
    <out>.json       — full schema (tables, columns, PKs, FKs, unique, indexes)
    <out>.mermaid    — erDiagram suitable for rendering with Mermaid

Requires: psycopg2-binary  (pip install psycopg2-binary)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import fail, header, info, load_env, ok, resolve_postgres_dsn

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    fail("psycopg2-binary not installed — run: pip install psycopg2-binary")


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

COLUMNS_SQL = """
SELECT
    c.table_name,
    c.column_name,
    c.ordinal_position,
    c.data_type,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale,
    c.is_nullable,
    c.column_default,
    c.is_identity
FROM information_schema.columns c
WHERE c.table_schema = 'public'
ORDER BY c.table_name, c.ordinal_position
"""

PK_SQL = """
SELECT
    kcu.table_name,
    kcu.column_name,
    kcu.ordinal_position
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema    = kcu.table_schema
WHERE tc.constraint_type = 'PRIMARY KEY'
  AND tc.table_schema = 'public'
ORDER BY kcu.table_name, kcu.ordinal_position
"""

FK_SQL = """
SELECT
    kcu.table_name        AS from_table,
    kcu.column_name       AS from_column,
    ccu.table_name        AS to_table,
    ccu.column_name       AS to_column,
    tc.constraint_name
FROM information_schema.table_constraints  tc
JOIN information_schema.key_column_usage   kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema    = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
   AND tc.table_schema    = ccu.table_schema
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_schema = 'public'
ORDER BY kcu.table_name, kcu.column_name
"""

UNIQUE_SQL = """
SELECT
    tc.constraint_name,
    kcu.table_name,
    kcu.column_name,
    kcu.ordinal_position
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
   AND tc.table_schema    = kcu.table_schema
WHERE tc.constraint_type = 'UNIQUE'
  AND tc.table_schema = 'public'
ORDER BY kcu.table_name, tc.constraint_name, kcu.ordinal_position
"""

INDEX_SQL = """
SELECT
    t.relname        AS table_name,
    i.relname        AS index_name,
    ix.indisunique   AS is_unique,
    ix.indisprimary  AS is_primary,
    array_agg(a.attname ORDER BY k.ord) AS columns
FROM pg_class t
JOIN pg_index ix      ON ix.indrelid = t.oid
JOIN pg_class i       ON i.oid = ix.indexrelid
JOIN pg_namespace n   ON n.oid = t.relnamespace
JOIN LATERAL unnest(ix.indkey) WITH ORDINALITY AS k(attnum, ord)
    ON TRUE
JOIN pg_attribute a   ON a.attrelid = t.oid AND a.attnum = k.attnum
WHERE n.nspname = 'public'
  AND t.relkind = 'r'
GROUP BY t.relname, i.relname, ix.indisunique, ix.indisprimary
ORDER BY t.relname, i.relname
"""

CHECK_SQL = """
SELECT
    tc.table_name,
    tc.constraint_name,
    cc.check_clause
FROM information_schema.table_constraints tc
JOIN information_schema.check_constraints cc
    ON tc.constraint_name = cc.constraint_name
   AND tc.table_schema    = cc.constraint_schema
WHERE tc.constraint_type = 'CHECK'
  AND tc.table_schema = 'public'
  AND cc.check_clause NOT LIKE '%IS NOT NULL%'
ORDER BY tc.table_name, tc.constraint_name
"""

ENUM_SQL = """
SELECT
    t.typname AS enum_name,
    e.enumlabel AS enum_value,
    e.enumsortorder AS sort_order
FROM pg_type t
JOIN pg_enum e ON e.enumtypid = t.oid
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = 'public'
ORDER BY t.typname, e.enumsortorder
"""


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def collect_schema(cur: "psycopg2.cursor") -> dict:
    def rows(sql: str) -> list[dict]:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]

    # Tables
    tables: dict[str, dict] = {}

    for row in rows(COLUMNS_SQL):
        tbl = row["table_name"]
        if tbl not in tables:
            tables[tbl] = {"columns": [], "primary_key": [], "foreign_keys": [],
                           "unique_constraints": [], "indexes": [], "check_constraints": []}
        col: dict = {
            "name": row["column_name"],
            "position": row["ordinal_position"],
            "type": _format_type(row),
            "nullable": row["is_nullable"] == "YES",
        }
        if row["column_default"] is not None:
            col["default"] = row["column_default"]
        if row["is_identity"] == "YES":
            col["identity"] = True
        tables[tbl]["columns"].append(col)

    # Primary keys
    pk_map: dict[str, list[str]] = {}
    for row in rows(PK_SQL):
        pk_map.setdefault(row["table_name"], []).append(row["column_name"])
    for tbl, cols in pk_map.items():
        if tbl in tables:
            tables[tbl]["primary_key"] = cols

    # Foreign keys
    for row in rows(FK_SQL):
        tbl = row["from_table"]
        if tbl in tables:
            tables[tbl]["foreign_keys"].append({
                "column": row["from_column"],
                "references_table": row["to_table"],
                "references_column": row["to_column"],
                "constraint": row["constraint_name"],
            })

    # Unique constraints
    unique_groups: dict[tuple, list[str]] = {}
    for row in rows(UNIQUE_SQL):
        key = (row["table_name"], row["constraint_name"])
        unique_groups.setdefault(key, []).append(row["column_name"])
    for (tbl, cname), cols in unique_groups.items():
        if tbl in tables:
            tables[tbl]["unique_constraints"].append({
                "constraint": cname,
                "columns": cols,
            })

    # Indexes
    idx_groups: dict[tuple, dict] = {}
    for row in rows(INDEX_SQL):
        key = (row["table_name"], row["index_name"])
        idx_groups[key] = {
            "name": row["index_name"],
            "columns": list(row["columns"]),
            "unique": row["is_unique"],
            "primary": row["is_primary"],
        }
    for (tbl, _), idx in idx_groups.items():
        if tbl in tables:
            tables[tbl]["indexes"].append(idx)

    # Check constraints
    for row in rows(CHECK_SQL):
        tbl = row["table_name"]
        if tbl in tables:
            tables[tbl]["check_constraints"].append({
                "constraint": row["constraint_name"],
                "clause": row["check_clause"],
            })

    # Enums
    enums: dict[str, list[str]] = {}
    for row in rows(ENUM_SQL):
        enums.setdefault(row["enum_name"], []).append(row["enum_value"])

    return {
        "tables": tables,
        "enums": enums,
    }


def _format_type(row: dict) -> str:
    dtype = row["data_type"]
    if dtype == "character varying" and row["character_maximum_length"]:
        return f"varchar({row['character_maximum_length']})"
    if dtype == "numeric" and row["numeric_precision"]:
        if row["numeric_scale"]:
            return f"numeric({row['numeric_precision']},{row['numeric_scale']})"
        return f"numeric({row['numeric_precision']})"
    return dtype


# ---------------------------------------------------------------------------
# Mermaid generation
# ---------------------------------------------------------------------------

MERMAID_TYPE_MAP = {
    "integer": "int",
    "bigint": "bigint",
    "smallint": "smallint",
    "boolean": "boolean",
    "text": "text",
    "uuid": "uuid",
    "timestamp without time zone": "timestamp",
    "timestamp with time zone": "timestamptz",
    "date": "date",
    "double precision": "float",
    "real": "float",
    "jsonb": "jsonb",
    "json": "json",
    "bytea": "bytea",
}


def _mermaid_type(pg_type: str) -> str:
    if pg_type in MERMAID_TYPE_MAP:
        return MERMAID_TYPE_MAP[pg_type]
    if pg_type.startswith("character varying"):
        return "varchar"
    # Strip precision/length — Mermaid ATTRIBUTE_WORD rejects parentheses
    base = re.sub(r"\(.*\)", "", pg_type).strip()
    if base in MERMAID_TYPE_MAP:
        return MERMAID_TYPE_MAP[base]
    return base.replace(" ", "_")


def _safe_ident(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name)


def generate_mermaid(schema: dict) -> str:
    tables = schema["tables"]
    lines = ["erDiagram"]

    # Entity definitions
    for tbl_name, tbl in sorted(tables.items()):
        safe = _safe_ident(tbl_name)
        lines.append(f"    {safe} {{")
        pk_cols = set(tbl["primary_key"])
        fk_cols = {fk["column"] for fk in tbl["foreign_keys"]}
        for col in tbl["columns"]:
            cname = col["name"]
            ctype = _mermaid_type(col["type"])
            tags = []
            if cname in pk_cols:
                tags.append("PK")
            if cname in fk_cols:
                tags.append("FK")
            tag_str = ", ".join(tags)
            if tag_str:
                lines.append(f"        {ctype} {cname} \"{tag_str}\"")
            else:
                lines.append(f"        {ctype} {cname}")
        lines.append("    }")

    lines.append("")

    # Relationships (foreign keys)
    seen: set[str] = set()
    for tbl_name, tbl in sorted(tables.items()):
        for fk in tbl["foreign_keys"]:
            from_t = _safe_ident(tbl_name)
            to_t = _safe_ident(fk["references_table"])
            key = f"{from_t}_{to_t}_{fk['column']}"
            if key in seen:
                continue
            seen.add(key)
            label = fk["column"]
            lines.append(f"    {to_t} ||--o{{ {from_t} : \"{label}\"")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Document the WeftMark PostgreSQL schema")
    parser.add_argument("--env", default=None,
                        help="Path to .env file (default: .env.dev, then .env)")
    parser.add_argument("--out", default="docs/schema",
                        help="Output file prefix (default: docs/schema)")
    args = parser.parse_args()

    root = Path(__file__).parent.parent

    # Resolve env file
    if args.env:
        env_path = Path(args.env)
    else:
        env_path = root / ".env.dev"
        if not env_path.exists():
            env_path = root / ".env"

    info(f"Loading env from {env_path}")
    env = load_env(str(env_path))

    dsn = resolve_postgres_dsn(env)
    # Mask password in log output
    dsn_display = re.sub(r":([^:@]+)@", ":***@", dsn)
    info(f"Connecting to {dsn_display}")

    try:
        conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    except Exception as e:
        fail(f"Connection failed: {e}")

    with conn:
        with conn.cursor() as cur:
            header("Collecting schema …")
            schema = collect_schema(cur)

    conn.close()

    table_count = len(schema["tables"])
    enum_count = len(schema["enums"])
    ok(f"Found {table_count} tables, {enum_count} enums")

    # Resolve output paths
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.parent.mkdir(parents=True, exist_ok=True)

    json_path = out.with_suffix(".json")
    mermaid_path = out.with_suffix(".mermaid")

    # Write JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(schema, f, indent=2, default=str)
    ok(f"JSON schema   → {json_path}")

    # Write Mermaid
    diagram = generate_mermaid(schema)
    with open(mermaid_path, "w", encoding="utf-8") as f:
        f.write(diagram)
    ok(f"Mermaid diagram → {mermaid_path}")


if __name__ == "__main__":
    main()
