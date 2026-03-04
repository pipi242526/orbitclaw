import json

import pytest

from lunaeclaw.capabilities.tools.export import ExportFileTool


@pytest.mark.asyncio
async def test_export_file_writes_txt(tmp_path):
    tool = ExportFileTool(exports_dir=tmp_path)
    res = json.loads(await tool.execute(filename="notes.txt", content="hello", format="txt"))
    assert res["ok"] is True
    assert res["name"] == "notes.txt"
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_export_file_rejects_path_traversal(tmp_path):
    tool = ExportFileTool(exports_dir=tmp_path)
    res = json.loads(await tool.execute(filename="../oops.txt", content="x"))
    assert res["error"] == "invalid_filename"
