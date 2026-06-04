"""Word 文档章节解析：styleId → heading 级别"""
from __future__ import annotations

import io
import zipfile

from app.core.document_structure import (
    _heading_level_from_style,
    _parse_docx_style_index,
    _resolve_style_name,
    load_document_structured,
)

_STYLE_INDEX = {
    "2": {"name": "heading 1", "basedOn": ""},
    "3": {"name": "heading 2", "basedOn": ""},
    "4": {"name": "heading 3", "basedOn": ""},
    "9": {"name": "自定义文档标题", "basedOn": ""},
    "a1": {"name": "子标题样式", "basedOn": "4"},
}


def test_resolve_style_name_from_style_id():
    assert _resolve_style_name("2", _STYLE_INDEX) == "heading 1"
    assert _resolve_style_name("4", _STYLE_INDEX) == "heading 3"


def test_resolve_style_name_follows_based_on():
    assert _resolve_style_name("a1", _STYLE_INDEX) == "子标题样式"


def test_heading_level_from_inherited_style():
    assert _heading_level_from_style("a1", _STYLE_INDEX) == 3


def test_heading_level_from_numeric_style_id():
    assert _heading_level_from_style("2", _STYLE_INDEX) == 1
    assert _heading_level_from_style("3", _STYLE_INDEX) == 2
    assert _heading_level_from_style("4", _STYLE_INDEX) == 3


def test_heading_level_from_chinese_title_style():
    assert _heading_level_from_style("9", _STYLE_INDEX) == 1


def test_heading_level_without_style_index_still_works():
    assert _heading_level_from_style("Heading 2") == 2
    assert _heading_level_from_style("标题 3") == 3
    assert _heading_level_from_style("4") == 0


def _minimal_docx_bytes() -> bytes:
    """构造含 heading 1/2 styleId 的最小 docx。"""
    styles_xml = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="2"><w:name w:val="heading 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="3"><w:name w:val="heading 2"/></w:style>
</w:styles>"""
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="2"/></w:pPr><w:r><w:t>Module A</w:t></w:r></w:p>
    <w:p><w:r><w:t>Module A detail</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="3"/></w:pPr><w:r><w:t>Feature B</w:t></w:r></w:p>
    <w:p><w:r><w:t>Feature B detail</w:t></w:r></w:p>
  </w:body>
</w:document>""".encode("utf-8")
    content_types = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
    rels = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    doc_rels = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/styles.xml", styles_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
    return buf.getvalue()


def test_load_docx_structured_recognizes_heading_style_ids():
    style_index = _parse_docx_style_index(_minimal_docx_bytes())
    assert style_index["2"]["name"] == "heading 1"

    result = load_document_structured(_minimal_docx_bytes(), "demo.docx")
    assert len(result.sections) == 2
    assert result.sections[0]["title"] == "Module A"
    assert result.sections[0]["level"] == 1
    assert result.sections[1]["title"] == "Feature B"
    assert result.sections[1]["level"] == 2
