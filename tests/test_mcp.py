"""Unit tests for mcp_server.py: JSON-RPC 2.0 MCP protocol and tool calls."""
from __future__ import annotations

import json
from pathlib import Path

from finsight.mcp_server import process_message
from finsight.schemas import FilingMeta, Financials, Provenance, Sourced


def _sample_financials() -> Financials:
    prov = Provenance(page=1, modality="text_table", verbatim="Total Assets 1000", bbox=[0.1, 0.1, 0.5, 0.2], bbox_source="text_layer")
    meta = FilingMeta(
        company="MCP Test Corp",
        currency="USD",
        unit_scale="millions",
        period_end="2024-12-31",
        basis="consolidated",
        standard="US_GAAP",
    )
    return Financials(
        meta=meta,
        total_assets=Sourced(value=1000.0, prov=prov),
        total_liabilities=Sourced(value=600.0, prov=prov),
        total_equity=Sourced(value=400.0, prov=prov),
        revenue=Sourced(value=1200.0, prov=prov),
        ebit=Sourced(value=240.0, prov=prov),
        net_income=Sourced(value=160.0, prov=prov),
        cfo=Sourced(value=180.0, prov=prov),
        capex=Sourced(value=50.0, prov=prov),
        cash=Sourced(value=100.0, prov=prov),
        current_assets=Sourced(value=400.0, prov=prov),
        current_liabilities=Sourced(value=250.0, prov=prov),
    )


def test_mcp_initialize():
    req = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
    resp = process_message(req)
    assert resp["id"] == 1
    assert "protocolVersion" in resp["result"]
    assert resp["result"]["serverInfo"]["name"] == "finsight-mcp"


def test_mcp_tools_list():
    req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    resp = process_message(req)
    assert resp["id"] == 2
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "audit_filing" in tool_names
    assert "audit_chart_image" in tool_names
    assert "calculate_dcf" in tool_names


def test_mcp_tool_call_chart_audit():
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "audit_chart_image",
            "arguments": {
                "values": [100.0, 110.0],
                "axis_min": 90.0,  # 90% truncated baseline!
            },
        },
    }
    resp = process_message(req)
    assert resp["id"] == 3
    content_text = resp["result"]["content"][0]["text"]
    audit_data = json.loads(content_text)
    assert audit_data["flagged"] is True
    assert audit_data["verdict"] == "distorted"
    assert audit_data["pairs"][0]["lie_factor"] > 1.05


def test_mcp_tool_call_dcf():
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "calculate_dcf",
            "arguments": {
                "revenue0": 1000.0,
                "price": 100.0,
                "wacc": 0.09,
                "terminal_growth": 0.03,
            },
        },
    }
    resp = process_message(req)
    assert resp["id"] == 4
    content_text = resp["result"]["content"][0]["text"]
    dcf_res = json.loads(content_text)
    assert "intrinsic_value_per_share" in dcf_res
    assert "monte_carlo" in dcf_res
    assert dcf_res["intrinsic_value_per_share"] > 0


def test_mcp_tool_call_audit_filing(tmp_path: Path):
    ws = tmp_path / "ws_mcp"
    ws.mkdir()
    fin = _sample_financials()
    (ws / "financials.json").write_text(fin.model_dump_json(indent=2), encoding="utf-8")

    req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "audit_filing",
            "arguments": {
                "workspace": str(ws),
            },
        },
    }
    resp = process_message(req)
    assert resp["id"] == 5
    content_text = resp["result"]["content"][0]["text"]
    forensics = json.loads(content_text)
    assert "altman_z_double_prime" in forensics
    assert "dupont5" in forensics
    assert "disclaimer" in forensics


def test_mcp_unknown_method():
    req = {"jsonrpc": "2.0", "id": 99, "method": "unknown/method", "params": {}}
    resp = process_message(req)
    assert resp["id"] == 99
    assert resp["error"]["code"] == -32601
