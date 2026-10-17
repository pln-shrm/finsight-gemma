"""Model Context Protocol (MCP) stdio server for FinSight-Gemma.

Exposes FinSight filing audit, chart forensics, and DCF valuation as standard MCP tools.
Implements JSON-RPC 2.0 stdio transport (MCP specification) without external dependencies.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .dcf import DCFInputs, monte_carlo, sensitivity_matrix, value_per_share
from .forensics import run_all
from .schemas import Financials

MCP_TOOLS = [
    {
        "name": "audit_filing",
        "description": "Run forensic financial audit (DuPont, Altman Z'', Beneish M, Piotroski F, flags) on extracted financials.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "workspace": {
                    "type": "string",
                    "description": "Path to workspace directory containing financials.json",
                },
                "market_cap": {
                    "type": "number",
                    "description": "Optional market cap in filing units for original Altman Z-score",
                },
            },
            "required": ["workspace"],
        },
    },
    {
        "name": "audit_chart_image",
        "description": "Audit a visual chart image for Lie Factor distortions and baseline truncations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "values": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Printed numerical values for the bars in the chart",
                },
                "axis_min": {
                    "type": "number",
                    "description": "Labeled minimum on the vertical axis (e.g. 0.0 or truncated)",
                },
            },
            "required": ["values", "axis_min"],
        },
    },
    {
        "name": "calculate_dcf",
        "description": "Run distribution-first DCF valuation sensitivity and Monte Carlo simulation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "revenue0": {"type": "number", "description": "Base year revenue"},
                "price": {"type": "number", "description": "Current stock price"},
                "wacc": {"type": "number", "description": "Cost of capital, e.g. 0.09"},
                "terminal_growth": {"type": "number", "description": "Perpetual growth, e.g. 0.03"},
                "ebit": {"type": "number", "description": "Base year EBIT"},
                "net_debt": {"type": "number", "description": "Debt minus cash"},
                "shares": {"type": "number", "description": "Diluted shares outstanding"},
            },
            "required": ["revenue0", "price"],
        },
    },
]


def handle_tool_call(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute the requested tool and return a structured JSON result."""
    if name == "audit_filing":
        ws = Path(arguments["workspace"])
        fin_file = ws / "financials.json"
        if not fin_file.exists():
            return {"error": f"Missing {fin_file}. Run extraction first."}

        fin = Financials.model_validate_json(fin_file.read_text(encoding="utf-8"))
        res = run_all(fin, market_cap=arguments.get("market_cap"))
        return res

    elif name == "audit_chart_image":
        from .lie_factor import lie_factor_from_axis

        vals = arguments.get("values", [])
        axis_min = arguments.get("axis_min", 0.0)
        if len(vals) < 2:
            return {"error": "Need at least 2 values to compute Lie Factor."}

        pairs = []
        for i in range(len(vals) - 1):
            lf_res = lie_factor_from_axis(vals[i], vals[i + 1], axis_min)
            pairs.append({"from": vals[i], "to": vals[i + 1], **lf_res.__dict__})

        flagged = any(p["verdict"] == "distorted" for p in pairs)
        return {
            "axis_min": axis_min,
            "pairs": pairs,
            "flagged": flagged,
            "verdict": "distorted" if flagged else "faithful",
        }

    elif name == "calculate_dcf":
        rev0 = float(arguments["revenue0"])
        price = float(arguments["price"])
        wacc = float(arguments.get("wacc", 0.10))
        g = float(arguments.get("terminal_growth", 0.03))
        ebit = float(arguments.get("ebit", rev0 * 0.15))
        net_debt = float(arguments.get("net_debt", 0.0))
        shares = float(arguments.get("shares", 100.0))

        margin = ebit / rev0 if rev0 else 0.15
        dcf_in = DCFInputs(
            revenue0=rev0,
            growth_start=0.10,
            growth_terminal=g,
            margin_start=margin,
            margin_target=margin,
            tax_rate=0.25,
            sales_to_capital=2.0,
            wacc=wacc,
            net_debt=net_debt,
            shares=shares,
        )

        base_val = value_per_share(dcf_in)
        sens = sensitivity_matrix(dcf_in, waccs=[wacc - 0.02, wacc, wacc + 0.02], gs=[g - 0.01, g, g + 0.01])
        mc = monte_carlo(dcf_in, n=3000, price=price)

        return {
            "intrinsic_value_per_share": base_val,
            "price": price,
            "sensitivity": sens,
            "monte_carlo": mc,
        }

    else:
        return {"error": f"Unknown tool: {name}"}


def process_message(msg: dict[str, Any]) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 message."""
    method = msg.get("method")
    msg_id = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "finsight-mcp", "version": "0.1.0"},
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"tools": MCP_TOOLS},
        }

    elif method == "tools/call":
        params = msg.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})
        res = handle_tool_call(tool_name, args)
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(res, indent=2)}],
                "isError": "error" in res,
            },
        }

    elif method == "notifications/initialized":
        return None

    else:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }


def run_stdio_server() -> None:
    """Run interactive stdio JSON-RPC server loop."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = process_message(req)
            if resp is not None:
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
        except json.JSONDecodeError:
            err = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}}
            sys.stdout.write(json.dumps(err) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    run_stdio_server()
