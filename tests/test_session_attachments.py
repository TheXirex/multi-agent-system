import asyncio
import base64
import json
from pathlib import Path
from sqlalchemy import create_engine, text
from agents.db_agent.config import get_settings as get_db_settings
from agents.db_agent.tools import IngestTabularFileTool
from agents.ml_agent.agent import create_ml_agent
from backend import QueryRequest, app
from httpx import AsyncClient, ASGITransport

async def run_verification():
    print("--- 1. Testing IngestTabularFileTool with session_id ---")
    db_cfg = get_db_settings()
    engine = create_engine(db_cfg.database_url)
    
    test_csv = Path("test_data/valid_customers.csv")
    assert test_csv.exists(), "test_data/valid_customers.csv not found"
    csv_bytes = test_csv.read_bytes()
    
    sess_a = "test-session-aaa-111"
    sess_b = "test-session-bbb-222"
    
    tool = IngestTabularFileTool(engine=engine)
    res_a = tool.execute(file_bytes=csv_bytes, filename="session_a_customers.csv", session_id=sess_a)
    assert res_a["status"] == "success", f"Ingest failed: {res_a}"
    t_name_a = res_a["table_name"]
    print(f"Session A table created: table_name={t_name_a}, session_id={res_a['session_id']}")
    
    with engine.connect() as conn:
        clean_id = "".join(c if c.isalnum() else "_" for c in sess_a.lower())
        schema_a = f"session_{clean_id}"
        count = conn.execute(
            text(f'SELECT COUNT(*) FROM "{schema_a}"."{t_name_a}"')
        ).scalar()
        assert count > 0, f"Expected rows in {schema_a}.{t_name_a}"
        print(f"Verified DB table '{schema_a}.{t_name_a}' has {count} rows")
        
    print("\n--- 2. Testing MLAgent session scoping ---")
    ml_agent = create_ml_agent(engine=engine)
    
    # Query within session A -> must find the table
    dfs_a, matched_a, all_a = ml_agent._resolve_in_memory_datasets(
        table_names=[t_name_a],
        session_id=sess_a,
    )
    assert len(dfs_a) > 0, "Expected non-empty dfs"
    print(f"Session A successfully resolved its table '{t_name_a}'")
    
    # Query within session B for table A -> must NOT find it!
    dfs_b, matched_b, all_b = ml_agent._resolve_in_memory_datasets(
        table_names=[t_name_a],
        session_id=sess_b,
    )
    assert len(dfs_b) == 0, f"Session B should NOT have access to table {t_name_a} from session A!"
    print(f"Session B correctly blocked from accessing session A table '{t_name_a}'")

    print("\n--- 3. Testing API /api/query with base64 attachment ---")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        b64_data = base64.b64encode(csv_bytes).decode("utf-8")
        req_payload = {
            "query": "Cluster these customers by age and annual_income into 3 clusters and create a chart",
            "session_id": "test-session-flow-999",
            "attachments": [
                {
                    "filename": "attached_customers.csv",
                    "content_base64": b64_data,
                }
            ]
        }
        resp = await ac.post("/api/query", json=req_payload)
        assert resp.status_code == 200, f"Query endpoint failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        print(f"Query returned response successfully!")
        print(f"Session ID returned: {data.get('session_id')}")
        print(f"Metadata: {data.get('metadata')}")
        
        # Verify message stored with attachment metadata
        with engine.connect() as conn:
            user_msg = conn.execute(
                text("SELECT content, metadata FROM internal.chat_messages WHERE session_id = 'test-session-flow-999' AND role = 'user' ORDER BY id DESC LIMIT 1")
            ).fetchone()
            assert user_msg is not None
            meta_json = json.loads(user_msg[1]) if isinstance(user_msg[1], str) else user_msg[1]
            assert "attachments" in meta_json, f"Missing attachments in user message metadata: {meta_json}"
            assert meta_json["attachments"][0]["filename"] == "attached_customers.csv"
            print(f"Verified user message metadata contains attachment: {meta_json['attachments']}")

    print("\nALL VERIFICATION CHECKS PASSED PERFECTLY!")

if __name__ == "__main__":
    asyncio.run(run_verification())
