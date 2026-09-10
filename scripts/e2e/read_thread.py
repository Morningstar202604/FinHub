"""Read a FinHub thread's full conversation from LangGraph checkpoints.

Usage: python scripts/e2e/read_thread.py <thread_id>
Decodes msgpack blobs from checkpoint_writes and prints the message flow
in readable form (role, tool calls, content).
"""
from __future__ import annotations

import msgpack
import sys
from pathlib import Path

import psycopg2

THREAD_ID = sys.argv[1] if len(sys.argv) > 1 else None
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
import os

load_dotenv(ROOT / ".env")

conn = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME", "finhub"),
    user=os.getenv("DB_USER", "finhub"),
    password=os.getenv("DB_PASSWORD", "finhub"),
)

cur = conn.cursor()
cur.execute(
    """
    SELECT idx, task_id, channel, type, blob
    FROM checkpoint_writes
    WHERE thread_id = %s AND channel = 'messages'
    ORDER BY checkpoint_ns, idx
    """,
    (THREAD_ID,),
)
rows = cur.fetchall()
print(f"# {len(rows)} message-checkpoint writes\n")


def render_message(m: dict) -> None:
    mtype = m.get("type", "?")
    if mtype == "human":
        print("👤 USER:", str(m.get("content", ""))[:1200])
    elif mtype == "ai":
        content = str(m.get("content") or "")
        name = m.get("name")
        meta = m.get("response_metadata") or {}
        model = meta.get("model_name") or meta.get("model")
        prefix = f"🤖 {name} " if name else "🤖 "
        model_txt = f" [{model}]" if model else ""
        print(f"{prefix}{model_txt}: {content[:1500]}")
        # tool calls
        for tc in m.get("tool_calls") or []:
            tname = tc.get("name")
            targs = tc.get("args") or {}
            print(f"   🔧 CALL {tname}({str(targs)[:300]})")
    elif mtype == "tool":
        print(f"   📦 TOOL[{m.get('name', '?')}] → {str(m.get('content', ''))[:600]}")
    else:
        print(f"[{mtype}] {str(m)[:300]}")


for idx, task_id, channel, typ, blob in rows:
    try:
        payload = msgpack.unpackb(bytes(blob), raw=False)
        if isinstance(payload, list):
            for m in payload:
                render_message(m)
        elif isinstance(payload, dict):
            render_message(payload)
    except Exception as e:  # noqa: BLE001
        print(f"[decode-error idx={idx}] {e}")