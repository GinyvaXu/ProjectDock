from __future__ import annotations

from projectdock.db import connect, delete_project, get_project, list_projects, upsert_project


def test_upsert_and_query(tmp_path):
    conn = connect(tmp_path / "data.db")
    upsert_project(conn, "项目1-软件-A", "项目1-软件-A", "软件", str(tmp_path / "a"), "描述", imported=False)
    assert get_project(conn, "项目1-软件-A")["description"] == "描述"
    assert len(list_projects(conn)) == 1
    upsert_project(conn, "项目1-软件-A", "项目1-软件-A", "软件", str(tmp_path / "a"), "新描述", imported=True)
    assert get_project(conn, "项目1-软件-A")["description"] == "新描述"
    delete_project(conn, "项目1-软件-A")
    row = get_project(conn, "项目1-软件-A")
    assert row is not None
    assert row["excluded"] == 1
