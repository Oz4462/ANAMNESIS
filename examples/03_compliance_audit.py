# Copyright (c) 2026 Ozan Küsmez. Licensed under Apache-2.0.
"""Print the EU AI Act compliance matrix the server serves at /v1/compliance/eu_ai_act.

Run with: uv run python examples/03_compliance_audit.py
"""

from __future__ import annotations

import json

from anamnesis_server.eu_compliance import compliance_matrix


def main() -> None:
    matrix = compliance_matrix()
    print(json.dumps(matrix, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
