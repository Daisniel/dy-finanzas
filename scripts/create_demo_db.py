from __future__ import annotations

"""Create a fully synthetic demo database for the public portfolio repository.

No production data is read or copied by this script.  All names, contacts,
addresses, financial amounts and operational records below are fictional.
"""

from datetime import date
from pathlib import Path
import math
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from impercontrol.database import Database  # noqa: E402

DEMO_PATH = ROOT / "data" / "demo.db"


def add(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    cur = conn.execute(sql, params)
    return int(cur.lastrowid)


def main() -> None:
    DEMO_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DEMO_PATH.exists():
        DEMO_PATH.unlink()

    db = Database(DEMO_PATH)

    with db.connection() as conn:
        # Portfolio-friendly settings. These are synthetic demonstration values.
        conn.execute("UPDATE settings SET value='3500' WHERE key='cash_opening_balance'")
        conn.execute("UPDATE settings SET value='10' WHERE key='price_new'")
        conn.execute("UPDATE settings SET value='6' WHERE key='price_maintenance'")
        conn.execute("UPDATE settings SET value='90' WHERE key='maintenance_warning_days'")

        crews = {row["name"]: int(row["id"]) for row in conn.execute("SELECT id,name FROM crews")}
        workers = {row["name"]: int(row["id"]) for row in conn.execute("SELECT id,name FROM workers")}
        materials = {row["name"]: int(row["id"]) for row in conn.execute("SELECT id,name FROM materials")}

        # ------------------------------------------------------------------
        # Clients: deliberately generic names/contacts/addresses.
        # ------------------------------------------------------------------
        client_ids: list[int] = []
        for index in range(1, 16):
            client_ids.append(add(
                conn,
                "INSERT INTO clients(name, phone, address, notes) VALUES (?,?,?,?)",
                (
                    f"Cliente Demo {index:02d}",
                    f"000-000-{index:04d}",
                    f"Dirección Demo {index:02d}, Mérida, Yucatán",
                    "Registro ficticio creado exclusivamente para la demostración pública.",
                ),
            ))

        # ------------------------------------------------------------------
        # Materials purchases provide enough inventory for the demo workflow.
        # ------------------------------------------------------------------
        mesh_id = materials["Malla de refuerzo 100 m"]
        paint19_id = materials["Pintura impermeabilizante 19 L"]
        paint16_id = materials["Pintura impermeabilizante 16 L"]

        purchases = [
            ("2026-01-03", mesh_id, 40.0, 0.0, 105.0, 4200.0, "Proveedor Demo A", "Marca Demo M", "Pagado", 4200.0),
            ("2026-01-03", paint19_id, 120.0, 2280.0, 82.0, 9840.0, "Proveedor Demo A", "Marca Demo 19", "Pago parcial", 6500.0),
            ("2026-01-04", paint16_id, 70.0, 1120.0, 69.0, 4830.0, "Proveedor Demo B", "Marca Demo 16", "Pagado", 4830.0),
            ("2026-06-05", paint19_id, 45.0, 855.0, 88.0, 3960.0, "Proveedor Demo C", "Marca Demo 19", "Pago parcial", 2200.0),
        ]
        purchase_ids: list[int] = []
        for p in purchases:
            movement_id = add(
                conn,
                """INSERT INTO material_movements(
                    movement_date, material_id, movement_type, quantity, liters,
                    unit_cost, total_cost, supplier, brand, payment_status, amount_paid, notes
                ) VALUES (?,?,'Compra',?,?,?,?,?,?,?,?,?)""",
                (*p[:6], p[6], p[7], p[8], p[9], "Compra ficticia para demostración"),
            )
            purchase_ids.append(movement_id)
            if p[9] > 0:
                conn.execute(
                    "INSERT INTO material_purchase_payments(movement_id,payment_date,amount,notes) VALUES (?,?,?,?)",
                    (movement_id, p[0], p[9], "Pago demo registrado al comprar"),
                )

        # Linked supplier debts for the two partial purchases.
        for movement_id in (purchase_ids[1], purchase_ids[3]):
            row = conn.execute("SELECT * FROM material_movements WHERE id=?", (movement_id,)).fetchone()
            conn.execute(
                """INSERT INTO debts(
                    creditor, debt_date, total_amount, amount_paid, debt_type,
                    material_movement_id, notes
                ) VALUES (?,?,?,?,?,?,?)""",
                (
                    row["supplier"], row["movement_date"], row["total_cost"], row["amount_paid"],
                    "Materiales", movement_id, "Deuda sintética vinculada a una compra demo.",
                ),
            )

        # ------------------------------------------------------------------
        # Measurements + jobs across 2023 and 2026 so every status/report is visible.
        # ------------------------------------------------------------------
        jobs_spec = [
            # measured, completion, maintenance, new, maint, status, crew, start
            ("2023-09-05", "2023-09-18", "2026-09-25", 180.0, 0.0, "Finalizado", "Brigada 1", "2023-09-12"),
            ("2026-01-07", "2026-01-16", "2029-01-16", 140.0, 30.0, "Finalizado", "Brigada 1", "2026-01-12"),
            ("2026-02-03", "2026-02-14", "2029-02-14", 90.0, 70.0, "Finalizado", "Brigada 2", "2026-02-10"),
            ("2026-03-05", "2026-03-21", "2029-03-21", 210.0, 0.0, "Finalizado", "Brigada 1", "2026-03-16"),
            ("2026-04-02", "2026-04-17", "2029-04-17", 0.0, 240.0, "Finalizado", "Brigada 2", "2026-04-13"),
            ("2026-05-04", "2026-05-20", "2029-05-20", 160.0, 40.0, "Finalizado", "Brigada 1", "2026-05-14"),
            ("2026-06-06", "2026-06-19", "2029-06-19", 185.0, 0.0, "Finalizado", "Brigada 2", "2026-06-15"),
            ("2026-07-05", "2026-07-23", "2029-07-23", 120.0, 80.0, "Finalizado", "Brigada 1", "2026-07-18"),
            ("2026-08-01", "2026-08-19", "2029-08-19", 200.0, 50.0, "Finalizado", "Brigada 2", "2026-08-12"),
            ("2026-09-01", "2026-09-07", "2029-09-07", 135.0, 65.0, "Finalizado", "Brigada 1", "2026-09-04"),
            ("2026-09-02", "2026-09-11", "2029-09-11", 220.0, 0.0, "Finalizado", "Brigada 2", "2026-09-08"),
            ("2026-09-06", None, None, 150.0, 30.0, "En Progreso", "Brigada 1", "2026-09-10"),
            ("2026-09-09", None, None, 110.0, 0.0, "Confirmado", "Brigada 2", "2026-09-20"),
            ("2026-09-12", None, None, 160.0, 0.0, "Medido", None, None),
        ]

        job_ids: list[int] = []
        job_rows: list[dict[str, float | int | str | None]] = []
        for idx, spec in enumerate(jobs_spec, start=1):
            measured, completed, maintenance_due, new_area, maintenance_area, status, crew_name, start_date = spec
            total_area = new_area + maintenance_area
            masonry_extra = 120.0 if idx in {4, 9} else 0.0
            membrane_extra = 85.0 if idx in {6, 10} else 0.0
            adjustment = -50.0 if idx == 8 else 0.0
            final_price = round(new_area * 10.0 + maintenance_area * 6.0 + masonry_extra + membrane_extra + adjustment, 2)
            client_id = client_ids[idx - 1]
            raw_text = (
                f"Techo principal: {round(max(total_area * 0.72, 1), 2)} m²\n"
                f"Área secundaria: {round(max(total_area * 0.28, 0), 2)} m²"
            )
            measurement_id = add(
                conn,
                """INSERT INTO measurements(
                    client_id, measured_date, raw_text, new_area, maintenance_area,
                    total_area, price_new, price_maintenance, masonry_extra,
                    membrane_extra, manual_adjustment, final_price, status, notes
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    client_id, measured, raw_text, new_area, maintenance_area, total_area,
                    10.0, 6.0, masonry_extra, membrane_extra, adjustment, final_price,
                    status, "Medición sintética para demostrar el flujo de trabajo.",
                ),
            )
            # Two deterministic measurement lines keep the detail page populated.
            part1 = round(total_area * 0.72, 2)
            part2 = round(total_area - part1, 2)
            conn.execute(
                """INSERT INTO measurement_lines(
                    measurement_id, original_text, expression, result, work_type, section, observation
                ) VALUES (?,?,?,?,?,?,?)""",
                (measurement_id, f"{part1}", f"{part1}", part1, "Desde cero" if new_area else "Mantenimiento", "Techo", "Área demo principal"),
            )
            if part2 > 0:
                conn.execute(
                    """INSERT INTO measurement_lines(
                        measurement_id, original_text, expression, result, work_type, section, observation
                    ) VALUES (?,?,?,?,?,?,?)""",
                    (measurement_id, f"{part2}", f"{part2}", part2, "Mantenimiento" if maintenance_area else "Desde cero", "Pretiles", "Área demo secundaria"),
                )

            crew_id = crews.get(crew_name) if crew_name else None
            code = f"DEMO-{measured[:4]}-{idx:04d}"
            job_id = add(
                conn,
                """INSERT INTO jobs(
                    code, measurement_id, client_id, crew_id, status, measurement_date,
                    scheduled_date, start_date, completion_date, maintenance_due_date,
                    new_area, maintenance_area, agreed_price, notes,
                    maintenance_contacted, materials_deducted
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    code, measurement_id, client_id, crew_id, status, measured,
                    start_date if status in {"Confirmado", "En Progreso", "Finalizado"} else None,
                    start_date, completed, maintenance_due, new_area, maintenance_area, final_price,
                    "Trabajo ficticio incluido en la base de demostración.", 0,
                    1 if status in {"En Progreso", "Finalizado"} else 0,
                ),
            )
            job_ids.append(job_id)
            job_rows.append({
                "id": job_id, "idx": idx, "status": status, "crew": crew_name,
                "new": new_area, "maint": maintenance_area, "total": total_area,
                "price": final_price, "start": start_date, "completed": completed,
            })

        # One extra client with a measurement that has not yet become a job.
        extra_client_id = client_ids[-1]
        extra_measurement = add(
            conn,
            """INSERT INTO measurements(
                client_id, measured_date, raw_text, new_area, maintenance_area, total_area,
                price_new, price_maintenance, final_price, status, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (extra_client_id, "2026-09-13", "10x8 + 4x3", 92.0, 0.0, 92.0, 10.0, 6.0, 920.0, "Medido", "Presupuesto demo aún sin convertir en trabajo."),
        )
        conn.executemany(
            """INSERT INTO measurement_lines(
                measurement_id, original_text, expression, result, work_type, section, observation
            ) VALUES (?,?,?,?,?,?,?)""",
            [
                (extra_measurement, "10x8", "10*8", 80.0, "Desde cero", "Techo", "Rectángulo principal"),
                (extra_measurement, "4x3", "4*3", 12.0, "Desde cero", "Techo", "Extensión"),
            ],
        )

        # ------------------------------------------------------------------
        # Planned/actual materials and worker payroll.
        # ------------------------------------------------------------------
        for row in job_rows:
            job_id = int(row["id"])
            total_area = float(row["total"])
            status = str(row["status"])
            if status == "Medido":
                continue

            mesh_qty = max(1, math.ceil(total_area / 100.0))
            # Alternate bucket size so both products appear in reports.
            paint_id = paint19_id if int(row["idx"]) % 3 else paint16_id
            bucket_size = 19.0 if paint_id == paint19_id else 16.0
            paint_qty = max(1, math.ceil(total_area / 25.0))
            conn.execute(
                "INSERT INTO job_material_plans(job_id,material_id,quantity,liters,notes) VALUES (?,?,?,?,?)",
                (job_id, mesh_id, float(mesh_qty), 0.0, "Plan demo de malla"),
            )
            conn.execute(
                "INSERT INTO job_material_plans(job_id,material_id,quantity,liters,notes) VALUES (?,?,?,?,?)",
                (job_id, paint_id, float(paint_qty), float(paint_qty) * bucket_size, "Plan demo de pintura"),
            )

            if status in {"En Progreso", "Finalizado"}:
                move_date = str(row["start"] or row["completed"] or "2026-09-10")
                conn.execute(
                    """INSERT INTO material_movements(
                        movement_date,material_id,movement_type,quantity,liters,unit_cost,total_cost,
                        job_id,payment_status,amount_paid,notes
                    ) VALUES (?,?, 'Consumo', ?,0,?,?,?,'No aplica',0,?)""",
                    (move_date, mesh_id, float(mesh_qty), 105.0, round(mesh_qty * 105.0, 2), job_id, "Consumo sintético ligado al trabajo demo"),
                )
                unit_cost = 82.0 if paint_id == paint19_id else 69.0
                conn.execute(
                    """INSERT INTO material_movements(
                        movement_date,material_id,movement_type,quantity,liters,unit_cost,total_cost,
                        job_id,payment_status,amount_paid,notes
                    ) VALUES (?,?, 'Consumo', ?,?,?,?,?,'No aplica',0,?)""",
                    (move_date, paint_id, float(paint_qty), float(paint_qty) * bucket_size, unit_cost, round(paint_qty * unit_cost, 2), job_id, "Consumo sintético ligado al trabajo demo"),
                )

            crew_name = row["crew"]
            if crew_name:
                if crew_name == "Brigada 1":
                    assigned = [
                        (workers["Jefe Brigada 1"], "Jefe / Administrador", 0.70, 0.30),
                        (workers["Ayudante Brigada 1"], "Ayudante", 0.50, 0.30),
                    ]
                else:
                    assigned = [
                        (workers["Jefe Brigada 2"], "Jefe", 0.60, 0.30),
                        (workers["Ayudante Brigada 2"], "Ayudante", 0.50, 0.30),
                    ]
                assigned.append((workers["Socio"], "Socio", 0.70, 0.30))
                for worker_id, role, rate_new, rate_maintenance in assigned:
                    base_pay = round(float(row["new"]) * rate_new + float(row["maint"]) * rate_maintenance, 2)
                    rounded_pay = round(base_pay)
                    final_pay = float(rounded_pay)
                    conn.execute(
                        """INSERT INTO job_workers(
                            job_id,worker_id,role,rate_new,rate_maintenance,base_pay,
                            rounded_pay,manual_adjustment,adjustment_reason,final_pay,paid,counts_for_worker_meters
                        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (job_id, worker_id, role, rate_new, rate_maintenance, base_pay, rounded_pay, 0.0, "", final_pay, 1 if status == "Finalizado" else 0, 1),
                    )

        # ------------------------------------------------------------------
        # Payments on completed jobs: advances + final payments, including a
        # non-cash foreign payment so that cash/reporting logic is visible.
        # ------------------------------------------------------------------
        for row in job_rows:
            if row["status"] != "Finalizado":
                continue
            price = float(row["price"])
            job_id = int(row["id"])
            start_date = str(row["start"])
            completed = str(row["completed"])
            advance = round(price * 0.30, 2)
            remainder = round(price - advance, 2)
            conn.execute(
                "INSERT INTO payments(payment_date,job_id,payment_type,amount,notes,affects_cash,tip_amount) VALUES (?,?,?,?,?,?,?)",
                (start_date, job_id, "Anticipo", advance, "Anticipo demo", 1, 0.0),
            )
            foreign = int(row["idx"]) == 8
            tip = 20.0 if int(row["idx"]) in {6, 10} else 0.0
            conn.execute(
                "INSERT INTO payments(payment_date,job_id,payment_type,amount,notes,affects_cash,tip_amount) VALUES (?,?,?,?,?,?,?)",
                (
                    completed, job_id,
                    "Pago final en el extranjero" if foreign else "Pago final",
                    remainder + tip,
                    "Pago final demo", 0 if foreign else 1, tip,
                ),
            )

        # ------------------------------------------------------------------
        # General expenses across the year.
        # ------------------------------------------------------------------
        expenses = [
            ("2026-01-12", "Combustible y traslados demo", 140.0, "Transporte", job_ids[1]),
            ("2026-02-11", "Herramientas menores demo", 95.0, "Herramientas", None),
            ("2026-03-18", "Transporte de materiales demo", 180.0, "Transporte", job_ids[3]),
            ("2026-04-10", "Mantenimiento de equipo demo", 125.0, "Reparación", None),
            ("2026-05-17", "Compra de consumibles demo", 85.0, "General", None),
            ("2026-06-14", "Transporte operativo demo", 165.0, "Transporte", job_ids[6]),
            ("2026-07-16", "Herramientas demo", 110.0, "Herramientas", None),
            ("2026-08-13", "Gasto operativo demo", 145.0, "General", None),
            ("2026-09-09", "Transporte de brigada demo", 175.0, "Transporte", job_ids[10]),
        ]
        conn.executemany(
            "INSERT INTO expenses(expense_date,description,amount,category,job_id) VALUES (?,?,?,?,?)",
            expenses,
        )

        # Material sale + inventory movement.
        sale_id = add(
            conn,
            "INSERT INTO material_sales(sale_date,customer,total_amount,notes) VALUES (?,?,?,?)",
            ("2026-08-25", "Cliente Mostrador Demo", 190.0, "Venta sintética para mostrar el módulo de materiales."),
        )
        conn.execute(
            "INSERT INTO material_sale_items(sale_id,material_id,quantity,unit_price,cost_unit,total_price) VALUES (?,?,?,?,?,?)",
            (sale_id, paint16_id, 2.0, 95.0, 69.0, 190.0),
        )
        conn.execute(
            """INSERT INTO material_movements(
                movement_date,material_id,movement_type,quantity,liters,unit_cost,total_cost,sale_id,
                payment_status,amount_paid,notes
            ) VALUES (?,?, 'Venta', ?,?,?,?,?,'No aplica',0,?)""",
            ("2026-08-25", paint16_id, 2.0, 32.0, 69.0, 138.0, sale_id, "Salida por venta demo"),
        )

        # Manual debt + one payment (separate from supplier material debts).
        debt_id = add(
            conn,
            "INSERT INTO debts(creditor,debt_date,total_amount,amount_paid,debt_type,notes) VALUES (?,?,?,?,?,?)",
            ("Acreedor Demo", "2026-07-02", 900.0, 300.0, "Préstamo", "Deuda ficticia para demostrar pagos y saldos."),
        )
        conn.execute(
            "INSERT INTO debt_payments(debt_id,payment_date,amount,notes,source) VALUES (?,?,?,?,?)",
            (debt_id, "2026-08-02", 300.0, "Abono demo", "Manual"),
        )

        # Receivable loan + repayment.
        loan_id = add(
            conn,
            "INSERT INTO loans_receivable(borrower,loan_date,total_amount,notes) VALUES (?,?,?,?)",
            ("Colaborador Demo", "2026-06-22", 500.0, "Préstamo ficticio para mostrar cuentas por cobrar."),
        )
        conn.execute(
            "INSERT INTO loan_repayments(loan_id,payment_date,amount,notes) VALUES (?,?,?,?)",
            (loan_id, "2026-08-22", 200.0, "Abono demo"),
        )

        # Manual cash movements.
        conn.executemany(
            "INSERT INTO cash_movements(movement_date,direction,category,amount,notes) VALUES (?,?,?,?,?)",
            [
                ("2026-03-01", "Entrada", "Aporte de otro negocio", 600.0, "Entrada ficticia para la demostración"),
                ("2026-05-28", "Salida", "Retiro personal", 250.0, "Salida ficticia para la demostración"),
                ("2026-09-12", "Entrada", "Ajuste de caja", 75.0, "Ajuste demo"),
            ],
        )

    # Re-run migrations/normalization to calculate material stock/average costs
    # exactly as the application will do when it opens the demo database.
    db.initialize()

    # Final integrity checks.
    with sqlite3.connect(DEMO_PATH) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity check failed: {integrity}")
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"Foreign-key check failed: {fk_errors}")

    print(f"Demo database created: {DEMO_PATH}")


if __name__ == "__main__":
    main()
