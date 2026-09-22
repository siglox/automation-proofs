#!/usr/bin/env python3
"""
Every test for this delivery, in one file. Standard library only.

    python3 tests/test_todo.py

Prints ALL TESTS OK and exits 0 when everything passes; prints exactly what
failed and exits 1 otherwise. Nothing to install, no account needed.

Each test below maps to an acceptance criterion in BRIEF.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import intake  # noqa: E402
import report  # noqa: E402


def solicitud(**campos):
    """A complete community application, with overrides."""
    base = {
        "category": "community",
        "applicant_name": "Ana Ruiz",
        "email": "ana@example.org",
        "organisation": "Barrio Norte",
        "amount_requested": 5000,
        "project_summary": "Community garden",
        "cycle": "2026-Q4",
    }
    base.update(campos)
    return base


def test_falta_un_campo_obligatorio():
    """Incompleta -> excepciones, diciendo qué falta."""
    r = intake.procesar([solicitud(project_summary="")])[0]
    fallos = []
    if r["status"] != intake.INCOMPLETE:
        fallos.append(f"expected INCOMPLETE, got {r['status']}")
    if "project_summary" not in r["missing_fields"]:
        fallos.append(f"missing field not reported: {r['missing_fields']}")
    return fallos


def test_obligatorios_dependen_de_la_categoria():
    """supervisor_email es obligatorio en research y no existe en community."""
    fallos = []
    sin_supervisor = solicitud(
        category="research", institution="Univ", research_abstract="x",
        organisation=None, supervisor_email=None)
    r = intake.procesar([sin_supervisor])[0]
    if r["status"] != intake.INCOMPLETE:
        fallos.append(f"research without supervisor should be INCOMPLETE, got {r['status']}")
    if "supervisor_email" not in r["missing_fields"]:
        fallos.append("supervisor_email should be reported missing for research")

    # La misma ausencia no debe penalizar a community.
    r2 = intake.procesar([solicitud()])[0]
    if r2["status"] != intake.ACCEPTED:
        fallos.append(f"community without supervisor should be ACCEPTED, got {r2['status']}")
    return fallos


def test_categoria_desconocida_va_a_excepciones():
    r = intake.procesar([solicitud(category="beca-rara")])[0]
    if r["status"] != intake.UNKNOWN_CATEGORY:
        return [f"expected UNKNOWN_CATEGORY, got {r['status']}"]
    if not r["history"]:
        return ["an unknown category must leave a history line"]
    return []


def test_email_invalido_no_se_acepta():
    r = intake.procesar([solicitud(email="no-es-un-email")])[0]
    if r["status"] != intake.INCOMPLETE:
        return [f"expected INCOMPLETE for a bad email, got {r['status']}"]
    return []


def test_duplicado_en_el_mismo_ciclo():
    resultados = intake.procesar([solicitud(), solicitud(applicant_name="Ana R.")])
    fallos = []
    if resultados[0]["status"] != intake.ACCEPTED:
        fallos.append(f"first submission should be ACCEPTED, got {resultados[0]['status']}")
    if resultados[1]["status"] != intake.DUPLICATE:
        fallos.append(f"second should be DUPLICATE, got {resultados[1]['status']}")
    if resultados[1].get("duplicate_of") != resultados[0]["application_id"]:
        fallos.append("the duplicate must point at the application it repeats")
    return fallos


def test_mismo_email_en_otro_ciclo_no_es_duplicado():
    resultados = intake.procesar([
        solicitud(cycle="2026-Q3"),
        solicitud(cycle="2026-Q4"),
    ])
    if resultados[1]["status"] == intake.DUPLICATE:
        return ["the same applicant may apply again in a different cycle"]
    return []


def test_el_duplicado_se_conserva():
    """Marcado, nunca borrado: solo una persona distingue reenvío de solicitud nueva."""
    resultados = intake.procesar([solicitud(), solicitud()])
    fallos = []
    if len(resultados) != 2:
        fallos.append(f"nothing may be dropped: expected 2 records, got {len(resultados)}")
    if not resultados[1].get("history"):
        fallos.append("the duplicate must carry a history explaining the decision")
    return fallos


def test_id_legible_unico_y_estable():
    resultados = intake.procesar([
        solicitud(email="a@example.org"),
        solicitud(email="b@example.org"),
        solicitud(category="emergency", email="c@example.org",
                  need_description="Roof collapsed", organisation=None),
    ])
    ids = [r["application_id"] for r in resultados]
    fallos = []
    if ids[0] != "COM-2026-Q4-0001":
        fallos.append(f"unexpected id format: {ids[0]}")
    if ids[1] != "COM-2026-Q4-0002":
        fallos.append(f"sequence should advance within a category: {ids[1]}")
    if not ids[2].startswith("EMG-"):
        fallos.append(f"each category has its own code: {ids[2]}")
    if len(set(ids)) != len(ids):
        fallos.append(f"ids must be unique: {ids}")
    # Estable: los mismos datos producen los mismos ids.
    otra_vez = [r["application_id"] for r in intake.procesar([
        solicitud(email="a@example.org"),
        solicitud(email="b@example.org"),
        solicitud(category="emergency", email="c@example.org",
                  need_description="Roof collapsed", organisation=None),
    ])]
    if ids != otra_vez:
        fallos.append("the same input must produce the same ids")
    return fallos


def test_la_secuencia_reinicia_en_cada_ciclo():
    """COM-2027-Q1-0001 tiene que ser la primera de ese ciclo, no la tercera."""
    resultados = intake.procesar([
        solicitud(email="a@example.org", cycle="2026-Q4"),
        solicitud(email="b@example.org", cycle="2026-Q4"),
        solicitud(email="c@example.org", cycle="2027-Q1"),
    ])
    ids = [r["application_id"] for r in resultados]
    if ids[2] != "COM-2027-Q1-0001":
        return [f"a new cycle must restart the sequence, got {ids[2]}"]
    return []


def test_importe_alto_va_a_revision():
    r = intake.procesar([solicitud(amount_requested=999999)])[0]
    if r["status"] != intake.NEEDS_REVIEW:
        return [f"an amount over the ceiling should be NEEDS_REVIEW, got {r['status']}"]
    return []


def test_nada_se_descarta_en_silencio():
    entradas = [
        solicitud(),
        solicitud(email="malo"),
        solicitud(category="inventada"),
        solicitud(),
        solicitud(category="research", institution="U", research_abstract="x",
                  supervisor_email="s@u.edu", email="otra@example.org"),
    ]
    resultados = intake.procesar(entradas)
    fallos = []
    if len(resultados) != len(entradas):
        fallos.append(f"expected {len(entradas)} results, got {len(resultados)}")
    for r in resultados:
        if not r.get("status"):
            fallos.append("every application must carry a status")
        if not r.get("history"):
            fallos.append(f"{r.get('application_id')}: every decision needs a history line")
    return fallos


def test_el_informe_cuadra():
    entradas = [
        solicitud(), solicitud(),
        solicitud(email="b@example.org", project_summary=""),
        solicitud(category="mala", email="c@example.org"),
    ]
    informe = report.contar(intake.procesar(entradas))
    fallos = []
    if informe["total"] != len(entradas):
        fallos.append(f"total mismatch: {informe['total']} != {len(entradas)}")
    if not informe["counts_add_up"]:
        fallos.append("by_status does not add up to the total")
    for clave in ("by_category", "by_cycle"):
        if sum(informe[clave].values()) != len(entradas):
            fallos.append(f"{clave} does not add up to the total")
    return fallos


def test_el_informe_solo_suma_importes_aceptados():
    entradas = [
        solicitud(amount_requested=1000),
        solicitud(email="b@example.org", amount_requested=5000, project_summary=""),
    ]
    informe = report.contar(intake.procesar(entradas))
    if informe["accepted_amount_total"] != 1000:
        return [f"only accepted amounts count: got {informe['accepted_amount_total']}"]
    return []


PRUEBAS = [
    test_falta_un_campo_obligatorio,
    test_obligatorios_dependen_de_la_categoria,
    test_categoria_desconocida_va_a_excepciones,
    test_email_invalido_no_se_acepta,
    test_duplicado_en_el_mismo_ciclo,
    test_mismo_email_en_otro_ciclo_no_es_duplicado,
    test_el_duplicado_se_conserva,
    test_id_legible_unico_y_estable,
    test_la_secuencia_reinicia_en_cada_ciclo,
    test_importe_alto_va_a_revision,
    test_nada_se_descarta_en_silencio,
    test_el_informe_cuadra,
    test_el_informe_solo_suma_importes_aceptados,
]


def main():
    fallos = []
    for prueba in PRUEBAS:
        try:
            for fallo in prueba():
                fallos.append(f"{prueba.__name__}: {fallo}")
        except Exception as e:
            fallos.append(f"{prueba.__name__}: raised {type(e).__name__}: {e}")

    print(f"{len(PRUEBAS)} tests run.")
    if fallos:
        print("FAILED:")
        for fallo in fallos:
            print(f"  - {fallo}")
        return 1
    print("ALL TESTS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
