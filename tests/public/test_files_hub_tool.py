import json

import pytest

from lunaeclaw.capabilities.tools.media import FilesHubTool


@pytest.mark.asyncio
async def test_files_hub_lists_media_and_exports(tmp_path):
    media = tmp_path / "media"
    exports = tmp_path / "exports"
    media.mkdir()
    exports.mkdir()
    (media / "abc123456789_report.pdf").write_text("x", encoding="utf-8")
    (exports / "summary.txt").write_text("ok", encoding="utf-8")

    tool = FilesHubTool(media_dir=media, exports_dir=exports)

    media_res = json.loads(await tool.execute(action="list", scope="media"))
    exports_res = json.loads(await tool.execute(action="list", scope="exports"))

    assert media_res["scope"] == "media"
    assert media_res["files"][0]["displayName"] == "report.pdf"
    assert exports_res["scope"] == "exports"
    assert exports_res["files"][0]["name"] == "summary.txt"


@pytest.mark.asyncio
async def test_files_hub_deletes_from_selected_scope(tmp_path):
    media = tmp_path / "media"
    exports = tmp_path / "exports"
    media.mkdir()
    exports.mkdir()
    (media / "keep.txt").write_text("bye", encoding="utf-8")
    (exports / "to_delete.txt").write_text("bye", encoding="utf-8")

    tool = FilesHubTool(media_dir=media, exports_dir=exports)
    result = json.loads(await tool.execute(action="delete", scope="exports", names=["to_delete.txt"]))

    assert result["action"] == "delete"
    assert result["scope"] == "exports"
    assert result["deleted"] == ["to_delete.txt"]
    assert not (exports / "to_delete.txt").exists()
    assert (media / "keep.txt").exists()
