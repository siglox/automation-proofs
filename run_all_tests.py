#!/usr/bin/env python3
"""Run every project's tests and print one line each.

Deliberately plain: standard library, no test runner to install, and it works
from a clean checkout on any machine with Python 3. Someone evaluating this
should be able to verify all of it with one command, before reading any code.

Exit code 0 only if every project passes.
"""

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent

# (carpeta, fichero de tests relativo a la carpeta)
PROYECTOS = [
    ("grant-intake", "tests/test_todo.py"),
    ("opt-in-relay", "test_demo.py"),
    ("email-to-crm-identity", "test_demo.py"),
    ("whatsapp-appointment-replies", "test_demo.py"),
    ("supplier-feed-normaliser", "test_supplier_sync.py"),
    ("bot-handoff-state-machine", "test_demo.py"),
]


def main():
    fallos = []
    print()
    for carpeta, test in PROYECTOS:
        ruta = RAIZ / carpeta / test
        if not ruta.exists():
            print(f"  {carpeta:<32} MISSING {test}")
            fallos.append(carpeta)
            continue

        # Cada test se ejecuta desde SU carpeta: varios leen fixtures por ruta
        # relativa, y correrlos desde la raiz los romperia sin que sea culpa del
        # codigo.
        cwd = ruta.parent
        res = subprocess.run(
            [sys.executable, ruta.name],
            cwd=cwd,
            capture_output=True,
            text=True,
        )
        salida = (res.stdout + res.stderr).strip().splitlines()
        ultima = salida[-1] if salida else "(no output)"
        estado = "ok " if res.returncode == 0 else "FAIL"
        print(f"  {estado}  {carpeta:<32} {ultima}")
        if res.returncode != 0:
            fallos.append(carpeta)

    print()
    if fallos:
        print(f"{len(fallos)} project(s) failing: {', '.join(fallos)}")
        return 1
    print(f"All {len(PROYECTOS)} projects pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
