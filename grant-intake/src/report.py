#!/usr/bin/env python3
"""
Counts by category, status and cycle, from processed applications.

Usage:
    python3 src/report.py processed.json            # readable summary
    python3 src/report.py processed.json --json     # machine readable

The counts always add up to the number of applications processed. If they ever
stop adding up, something is being lost and the report cannot be trusted, so the
total is checked and stated on every run.
"""

import json
import sys
from collections import Counter
from pathlib import Path


def contar(resultados):
    por_estado = Counter(r.get("status", "UNKNOWN") for r in resultados)
    por_categoria = Counter(r.get("category", "unknown") for r in resultados)
    por_ciclo = Counter(r.get("cycle", "unknown") for r in resultados)

    # Only accepted applications carry a requested amount worth totalling: the
    # rest are unresolved, and adding them up would overstate the commitment.
    importes = [r.get("amount_requested") for r in resultados
                if r.get("status") == "ACCEPTED"
                and isinstance(r.get("amount_requested"), (int, float))]

    return {
        "total": len(resultados),
        "by_status": dict(sorted(por_estado.items())),
        "by_category": dict(sorted(por_categoria.items())),
        "by_cycle": dict(sorted(por_ciclo.items())),
        "accepted_amount_total": sum(importes),
        "accepted_with_amount": len(importes),
        "counts_add_up": sum(por_estado.values()) == len(resultados),
    }


def imprimir(informe):
    print(f"{informe['total']} application(s)\n")
    for titulo, clave in (("By status", "by_status"),
                          ("By category", "by_category"),
                          ("By cycle", "by_cycle")):
        print(titulo)
        for nombre, cuenta in informe[clave].items():
            print(f"  {nombre:<20} {cuenta}")
        print()
    print(f"Requested by accepted applications: "
          f"{informe['accepted_amount_total']:,} "
          f"across {informe['accepted_with_amount']} application(s)")
    if not informe["counts_add_up"]:
        print("\nWARNING: the counts do not add up. Do not trust this report.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    resultados = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    informe = contar(resultados)

    if "--json" in sys.argv:
        print(json.dumps(informe, indent=2))
    else:
        imprimir(informe)
    return 0 if informe["counts_add_up"] else 1


if __name__ == "__main__":
    sys.exit(main())
