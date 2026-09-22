#!/usr/bin/env python3
"""
Grant application intake: validate, deduplicate, assign IDs, route.

Takes the raw form submissions and decides, for each one, whether it is complete
enough to go to the committee or needs a human to look at it first. Nothing is
ever discarded: every application comes out the other side either ACCEPTED or in
the exceptions queue, with a reason attached.

Usage:
    python3 src/intake.py submissions.json processed.json

Standard library only. No account, key or network access required: this runs on
files, so you can try it on real data without connecting it to anything.
"""

import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CONFIG = json.loads((RAIZ / "config.json").read_text(encoding="utf-8"))

# Statuses. ACCEPTED goes to the committee; everything else waits for a person.
ACCEPTED = "ACCEPTED"
INCOMPLETE = "INCOMPLETE"
DUPLICATE = "DUPLICATE"
UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"
NEEDS_REVIEW = "NEEDS_REVIEW"

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalizar_email(valor):
    """Case and stray spaces are the main reason duplicates survive."""
    return (valor or "").strip().lower()


def campos_obligatorios(categoria):
    """What this category must carry, plus what every category must carry."""
    definicion = CONFIG["categories"].get(categoria)
    if definicion is None:
        return None
    campos = list(definicion["required_fields"])
    for campo in CONFIG["always_required"]:
        if campo not in campos:
            campos.append(campo)
    return campos


def campos_que_faltan(solicitud, categoria):
    faltan = []
    for campo in campos_obligatorios(categoria) or []:
        valor = solicitud.get(campo)
        if valor is None or (isinstance(valor, str) and not valor.strip()):
            faltan.append(campo)
    return faltan


def construir_id(categoria, ciclo, secuencia):
    """Readable, unique and stable: COM-2026-Q4-0001.

    Readable matters more than short here: staff read these out on calls, and a
    random hash would make every conversation about the grant harder.
    """
    codigo = CONFIG["categories"][categoria]["code"]
    return f"{codigo}-{ciclo}-{secuencia:04d}"


def procesar(solicitudes):
    """Return every application with a status, an id where possible, and a trail.

    The order of checks is deliberate: category first, because without a valid
    category we cannot know what 'complete' even means for this application.
    """
    resultados = []
    secuencias = {}
    vistos = {}

    for entrada, solicitud in enumerate(solicitudes, start=1):
        ciclo = solicitud.get("cycle") or CONFIG["cycle"]["current"]
        categoria = (solicitud.get("category") or "").strip().lower()
        email = normalizar_email(solicitud.get("email"))
        historial = []

        procesada = dict(solicitud)
        procesada["cycle"] = ciclo
        procesada["submission_index"] = entrada
        procesada["application_id"] = None

        # 1. Category. Without it, nothing else can be judged.
        if categoria not in CONFIG["categories"]:
            historial.append(
                f"Routed to exceptions: category '{solicitud.get('category')}' "
                f"is not one of {', '.join(sorted(CONFIG['categories']))}.")
            procesada["status"] = UNKNOWN_CATEGORY
            procesada["missing_fields"] = []
            procesada["history"] = historial
            resultados.append(procesada)
            continue

        procesada["category"] = categoria
        historial.append(f"Category recognised as '{categoria}'.")

        # 2. Identity. An application with no usable email cannot be tracked,
        #    answered or deduplicated, so it goes to a person.
        if not EMAIL.match(email):
            historial.append(
                f"Routed to exceptions: '{solicitud.get('email')}' is not a "
                "usable email address.")
            procesada["status"] = INCOMPLETE
            procesada["missing_fields"] = ["email"]
            procesada["history"] = historial
            resultados.append(procesada)
            continue

        procesada["email"] = email

        # 3. Duplicates. Marked, never deleted: only a person can tell a
        #    resubmission from a second, legitimate application.
        clave = email if CONFIG["duplicate_scope"] == "ever" else (email, ciclo)
        if clave in vistos:
            original = vistos[clave]
            historial.append(
                f"Routed to exceptions: duplicate of {original} "
                f"({'same email, any cycle' if CONFIG['duplicate_scope'] == 'ever' else 'same email, same cycle'}). "
                "Kept for a human to resolve; nothing was deleted.")
            procesada["status"] = DUPLICATE
            procesada["duplicate_of"] = original
            procesada["missing_fields"] = []
            procesada["history"] = historial
            resultados.append(procesada)
            continue

        # 4. Completeness, according to this category's own rules.
        faltan = campos_que_faltan(solicitud, categoria)
        # Per category AND cycle: each new cycle starts again at 0001, which is
        # what anyone reading COM-2027-Q1-0001 expects it to mean.
        contador = (categoria, ciclo)
        secuencias[contador] = secuencias.get(contador, 0) + 1
        identificador = construir_id(categoria, ciclo, secuencias[contador])
        procesada["application_id"] = identificador
        vistos[clave] = identificador
        historial.append(f"Assigned application id {identificador}.")
        procesada["missing_fields"] = faltan

        if faltan:
            historial.append(
                "Routed to exceptions: missing required field(s): "
                f"{', '.join(faltan)}.")
            procesada["status"] = INCOMPLETE
            procesada["history"] = historial
            resultados.append(procesada)
            continue

        # 5. Anything unusual that is not strictly wrong goes to review rather
        #    than being accepted quietly.
        techo = CONFIG.get("amount_ceiling") or 0
        importe = solicitud.get("amount_requested")
        if techo and isinstance(importe, (int, float)) and importe > techo:
            historial.append(
                f"Routed to review: amount requested ({importe}) is above the "
                f"ceiling of {techo}.")
            procesada["status"] = NEEDS_REVIEW
            procesada["history"] = historial
            resultados.append(procesada)
            continue

        historial.append("All required fields present. Ready for the committee.")
        procesada["status"] = ACCEPTED
        procesada["history"] = historial
        resultados.append(procesada)

    return resultados


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        return 1

    solicitudes = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    if not isinstance(solicitudes, list):
        print(f"{sys.argv[1]}: expected a list of submissions.")
        return 1

    resultados = procesar(solicitudes)
    Path(sys.argv[2]).write_text(
        json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8")

    aceptadas = sum(1 for r in resultados if r["status"] == ACCEPTED)
    print(f"Processed {len(resultados)} submission(s).")
    print(f"  {aceptadas} ready for the committee")
    print(f"  {len(resultados) - aceptadas} in the exceptions queue")
    print(f"Written to {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
