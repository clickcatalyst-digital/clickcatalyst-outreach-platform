# api/routes/interactions.py
# Lead interaction log - works for any CIN (MCA or Places synthetic).

from fastapi import APIRouter, HTTPException
from ..database import get_conn

router = APIRouter()


@router.get("/{cin}")
def list_interactions(cin: str):
    """All interactions for a given lead, newest first."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT Interaction_ID, CIN, Comment, Interacted, Created_At, Created_By
        FROM lead_interactions
        WHERE CIN = ?
        ORDER BY Created_At DESC
    """, (cin,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"cin": cin, "interactions": rows, "count": len(rows)}


@router.post("/{cin}")
def create_interaction(cin: str, body: dict):
    """
    Log a new interaction.
    Body: {"comment": "Spoke with founder, interested in audit", "interacted": true}
    """
    comment = (body.get("comment") or "").strip()
    if not comment:
        raise HTTPException(status_code=400, detail="comment is required")

    interacted = bool(body.get("interacted", True))
    created_by = body.get("created_by", "ui")

    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO lead_interactions (CIN, Comment, Interacted, Created_By)
        VALUES (?, ?, ?, ?)
    """, (cin, comment, interacted, created_by))
    interaction_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return {"ok": True, "interaction_id": interaction_id, "cin": cin}


@router.delete("/{interaction_id}")
def delete_interaction(interaction_id: int):
    """Delete a specific interaction by ID."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM lead_interactions WHERE Interaction_ID = ?", (interaction_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Interaction not found")
    return {"ok": True, "deleted": deleted}