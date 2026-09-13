from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from impercontrol.database import Database
from impercontrol.formatters import format_date, round_area
from impercontrol.repositories import AppRepository
from impercontrol.services import ApplicationServices, MeasurementTotals


class CoreFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "impercontrol_test.db")
        self.repo = AppRepository(self.db)
        self.services = ApplicationServices(self.repo)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _create_measurement_and_job(self, new_area: float = 100, maintenance: float = 0) -> tuple[int, int, int]:
        client_id = self.repo.save_client("Cliente prueba", "555", "Dirección")
        rows = [
            {
                "original_text": "10 x 10",
                "expression": "10*10",
                "result": new_area,
                "section": "Techo",
                "work_type": "Desde cero",
                "observation": "",
            }
        ]
        totals = MeasurementTotals(new_area, maintenance, new_area + maintenance)
        price = self.services.measurements.calculate_price(totals, 10, 6, 0, 0, 0)
        measurement_id = self.services.measurements.save(
            client_id=client_id,
            measured_date="2026-08-01",
            raw_text="10 x 10",
            rows=rows,
            totals=totals,
            price_new=10,
            price_maintenance=6,
            masonry_extra=0,
            membrane_extra=0,
            manual_adjustment=0,
            final_price=price,
            status="Medido",
            notes="",
        )
        job_id = self.repo.upsert_job_from_measurement(
            measurement_id=measurement_id,
            client_id=client_id,
            status="Medido",
            new_area=new_area,
            maintenance_area=maintenance,
            agreed_price=price,
            notes="",
        )
        return client_id, measurement_id, job_id


    def _stock_all_materials(self, quantity: float = 10) -> dict[int, float]:
        before: dict[int, float] = {}
        for material in self.repo.list_materials():
            before[int(material["id"])] = float(quantity)
            liters = (
                quantity * float(material["package_size"])
                if material["category"] == "Pintura"
                else 0
            )
            self.repo.record_material_movement(
                movement_date="2026-08-01",
                material_id=material["id"],
                movement_type="Compra",
                quantity=quantity,
                liters=liters,
                unit_cost=20,
                total_cost=quantity * 20,
                job_id=None,
                supplier="Proveedor",
                payment_mode="Pagado",
                amount_paid=quantity * 20,
                notes="Stock de prueba",
            )
        return before

    def test_measurement_quote_and_single_job_registration(self) -> None:
        raw = """Techo
4.85 x 10.65
14.65 x 10.65

Pretiles
1.10 x 14.65 x 2
1 x 10.65
"""
        parsed = self.services.measurements.parse(raw)
        rows = [
            {
                "original_text": item.original_text,
                "expression": item.expression,
                "result": item.result,
                "section": item.section,
                "work_type": item.work_type,
                "observation": item.observation,
            }
            for item in parsed
        ]
        totals = self.services.measurements.totals_from_rows(rows)
        quote = self.services.measurements.build_whatsapp_quote(rows, round_area(totals.total_area), 2810)
        self.assertIn("Total del Techo", quote)
        self.assertIn("Total de Pretiles", quote)
        self.assertIn(f"{round_area(totals.total_area)} m²", quote)

        client_id = self.repo.save_client("Cliente", "123", "Dirección")
        measurement_id = self.services.measurements.save(
            client_id=client_id,
            measured_date="2026-08-01",
            raw_text=raw,
            rows=rows,
            totals=MeasurementTotals(round_area(totals.new_area), 0, round_area(totals.new_area)),
            price_new=10,
            price_maintenance=6,
            masonry_extra=0,
            membrane_extra=0,
            manual_adjustment=0,
            final_price=2810,
            status="Medido",
            notes="",
        )
        first_job = self.repo.upsert_job_from_measurement(
            measurement_id=measurement_id,
            client_id=client_id,
            status="Medido",
            new_area=281,
            maintenance_area=0,
            agreed_price=2810,
            notes="",
        )
        second_job = self.repo.upsert_job_from_measurement(
            measurement_id=measurement_id,
            client_id=client_id,
            status="Confirmado",
            new_area=280,
            maintenance_area=0,
            agreed_price=2800,
            notes="Actualizado",
        )
        self.assertEqual(first_job, second_job)
        self.assertEqual(self.repo.get_job(first_job)["status"], "Confirmado")
        self.assertEqual(len(self.repo.client_work_rows("Cliente")), 1)

    def test_whatsapp_quote_keeps_each_measure_and_total_on_one_line(self) -> None:
        rows = [
            {
                "expression": "10.90*6.40",
                "result": 69.76,
                "section": "Techo",
                "observation": "",
            },
            {
                "expression": "0.80*(2.60+4.80)",
                "result": 5.92,
                "section": "Pretiles",
                "observation": "Lateral",
            },
        ]
        quote = self.services.measurements.build_whatsapp_quote(rows, 75.68, 1760)
        self.assertEqual(
            quote,
            "Techo\n"
            "10.90 x 6.40 = 69,76\n"
            "Total del Techo 69,76 m²\n\n"
            "Pretiles\n"
            "0.80 x (2.60+4.80) (Lateral) = 5,92\n"
            "Total de Pretiles 5,92 m²\n\n"
            "Total del Área 76 m²\n\n"
            "Costo Total del trabajo 1760,00 USD",
        )

    def test_rounding_and_date_format(self) -> None:
        self.assertEqual(round_area(280.49), 280)
        self.assertEqual(round_area(280.50), 281)
        self.assertEqual(format_date("2026-08-01"), "01/08/2026")

    def test_payroll_and_maintenance_due_date(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        crew = self.repo.active_crews()[0]
        payroll = self.services.payroll.calculate_all(
            self.services.payroll.default_lines("Brigada 1"), 100, 0
        )
        self.assertEqual([line.final_pay for line in payroll], [70.0, 50.0, 70.0])
        self.services.payroll.save(job_id, payroll)
        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Finalizado",
            crew_id=crew["id"],
            measurement_date="2026-08-01",
            start_date="2026-08-02",
            completion_date="2026-08-03",
            agreed_price=1000,
            notes="",
        )
        self.assertEqual(self.repo.get_job(job_id)["maintenance_due_date"], "2029-08-03")

    def test_credit_purchase_payments_and_editing(self) -> None:
        material = self.repo.list_materials()[1]
        movement_id = self.repo.record_material_movement(
            movement_date="2026-08-01",
            material_id=material["id"],
            movement_type="Compra",
            quantity=4,
            liters=76,
            unit_cost=100,
            total_cost=400,
            job_id=None,
            supplier="Proveedor A",
            payment_mode="Pago parcial",
            amount_paid=100,
            notes="Compra a crédito",
        )
        movement = self.repo.get_material_movement(movement_id)
        self.assertEqual(float(movement["balance_due"]), 300)
        self.assertEqual(movement["payment_status"], "Pago parcial")

        self.repo.add_purchase_payment(movement_id, "2026-08-05", 150, "Primer abono")
        movement = self.repo.get_material_movement(movement_id)
        self.assertEqual(float(movement["amount_paid"]), 250)
        self.assertEqual(float(movement["balance_due"]), 150)
        self.assertEqual(len(self.repo.purchase_payments(movement_id)), 2)

        self.repo.update_material_movement(
            movement_id,
            movement_date="2026-08-01",
            material_id=material["id"],
            quantity=5,
            liters=95,
            unit_cost=100,
            total_cost=500,
            job_id=None,
            supplier="Proveedor A",
            target_paid=300,
            notes="Cantidad corregida",
        )
        movement = self.repo.get_material_movement(movement_id)
        self.assertEqual(float(movement["quantity"]), 5)
        self.assertEqual(float(movement["balance_due"]), 200)
        self.assertEqual(float(self.repo.list_materials()[1]["stock_quantity"]), 5)

    def test_completion_auto_deducts_materials_once(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        self._stock_all_materials(10)

        descriptions = self.repo.auto_consume_job_materials(job_id, 25, 100)
        self.assertEqual(len(descriptions), 2)
        stocks = {row["category"] + str(row["package_size"]): float(row["stock_quantity"]) for row in self.repo.list_materials()}
        self.assertEqual(stocks["Malla100.0"], 9)
        self.assertEqual(stocks["Pintura19.0"], 6)
        self.assertEqual(self.repo.job_material_consumption_count(job_id), 2)

        second = self.repo.auto_consume_job_materials(job_id, 25, 100)
        self.assertEqual(second, [])
        self.assertEqual(self.repo.job_material_consumption_count(job_id), 2)

    def test_delete_job_restores_materials_and_keeps_measurement_history(self) -> None:
        _client_id, measurement_id, job_id = self._create_measurement_and_job(100, 0)
        self._stock_all_materials(10)
        self.repo.ensure_job_material_plan(job_id, 25, 100)
        self.repo.auto_consume_job_materials(job_id, 25, 100)
        self.repo.add_payment(job_id, "2026-08-05", "Cobro", 100, "Prueba")

        self.repo.delete_job(job_id)

        self.assertIsNone(self.repo.get_job(job_id))
        self.assertIsNotNone(self.repo.get_measurement(measurement_id))
        self.assertEqual(self.repo.get_measurement(measurement_id)["status"], "Medido")
        self.assertEqual(self.repo.payments(job_id), [])
        self.assertEqual(self.repo.job_material_plan(job_id), [])
        self.assertEqual(self.repo.job_material_net_usage(job_id), [])
        self.assertTrue(all(float(row["stock_quantity"]) == 10 for row in self.repo.list_materials()))

    def test_job_edit_updates_client_areas_and_measurement(self) -> None:
        client_id, measurement_id, job_id = self._create_measurement_and_job(100, 10)
        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Confirmado",
            crew_id=self.repo.active_crews()[0]["id"],
            measurement_date="2026-08-02",
            start_date="2099-08-03",
            completion_date="2026-08-04",
            agreed_price=1300,
            notes="Corregido",
            new_area=120,
            maintenance_area=15,
            phone="555-999",
            address="Dirección corregida",
        )
        updated_job = self.repo.get_job(job_id)
        updated_client = self.repo.get_client(client_id)
        updated_measurement = self.repo.get_measurement(measurement_id)
        self.assertEqual(float(updated_job["new_area"]), 120)
        self.assertEqual(float(updated_job["maintenance_area"]), 15)
        self.assertEqual(updated_client["phone"], "555-999")
        self.assertEqual(updated_client["address"], "Dirección corregida")
        self.assertEqual(float(updated_measurement["total_area"]), 135)

    def test_job_measurement_breakdown_is_editable_and_persisted_with_totals(self) -> None:
        client_id = self.repo.save_client("Cliente con desglose", "555", "Dirección")
        initial_rows = [
            {
                "original_text": "10 x 10",
                "expression": "10*10",
                "result": 100,
                "section": "Techo",
                "work_type": "Desde cero",
                "observation": "Área principal",
            },
            {
                "original_text": "2 x 5",
                "expression": "2*5",
                "result": 10,
                "section": "Pretiles",
                "work_type": "Mantenimiento",
                "observation": "Lateral norte",
            },
        ]
        initial_totals = MeasurementTotals(100, 10, 110)
        measurement_id = self.services.measurements.save(
            client_id=client_id,
            measured_date="2026-08-01",
            raw_text="Techo\n10 x 10\n\nPretiles\n2 x 5",
            rows=initial_rows,
            totals=initial_totals,
            price_new=10,
            price_maintenance=6,
            masonry_extra=0,
            membrane_extra=0,
            manual_adjustment=0,
            final_price=1060,
            status="Medido",
            notes="",
        )
        job_id = self.repo.upsert_job_from_measurement(
            measurement_id=measurement_id,
            client_id=client_id,
            status="Medido",
            new_area=100,
            maintenance_area=10,
            agreed_price=1060,
            notes="",
        )

        edited_rows = [
            {
                "original_text": "12 x 10",
                "expression": "12*10",
                "result": 120,
                "section": "Techo",
                "work_type": "Desde cero",
                "observation": "Área principal corregida",
            },
            {
                "original_text": "3 x 5",
                "expression": "3*5",
                "result": 15,
                "section": "Pretiles",
                "work_type": "Mantenimiento",
                "observation": "Lateral norte ampliado",
            },
        ]
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=self.repo.get_job(job_id),
            status="Medido",
            crew_id=None,
            measurement_date="2026-08-01",
            start_date=None,
            agreed_price=1290,
            notes="Desglose corregido",
            new_area=120,
            maintenance_area=15,
            measurement_rows=edited_rows,
        )

        updated_job = self.repo.get_job(job_id)
        updated_measurement = self.repo.get_measurement(measurement_id)
        saved_lines = self.repo.measurement_lines(measurement_id)
        self.assertEqual(float(updated_job["new_area"]), 120)
        self.assertEqual(float(updated_job["maintenance_area"]), 15)
        self.assertEqual(float(updated_job["agreed_price"]), 1290)
        self.assertEqual(float(updated_measurement["total_area"]), 135)
        self.assertEqual(float(updated_measurement["final_price"]), 1290)
        self.assertEqual(len(saved_lines), 2)
        self.assertEqual(saved_lines[0]["expression"], "12*10")
        self.assertEqual(float(saved_lines[1]["result"]), 15)

    def test_legacy_job_without_measurement_gets_breakdown_on_save(self) -> None:
        client_id = self.repo.save_client("Cliente legado")
        job_id = self.db.execute(
            """INSERT INTO jobs(
            code, client_id, status, measurement_date, new_area,
            maintenance_area, agreed_price, notes
            ) VALUES (?, ?, 'Medido', ?, ?, ?, ?, ?)""",
            (self.db.next_job_code(), client_id, "2026-08-01", 50, 0, 500, ""),
        )
        rows = [{
            "original_text": "5 x 10",
            "expression": "5*10",
            "result": 50,
            "section": "Techo",
            "work_type": "Desde cero",
            "observation": "Migrada",
        }]
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=self.repo.get_job(job_id),
            status="Medido",
            crew_id=None,
            measurement_date="2026-08-01",
            start_date=None,
            agreed_price=500,
            notes="",
            new_area=50,
            maintenance_area=0,
            measurement_rows=rows,
        )
        updated_job = self.repo.get_job(job_id)
        self.assertIsNotNone(updated_job["measurement_id"])
        self.assertEqual(len(self.repo.measurement_lines(int(updated_job["measurement_id"]))), 1)

    def test_material_debt_is_linked_and_paid_from_debts(self) -> None:
        material = self.repo.list_materials()[1]
        movement_id = self.repo.record_material_movement(
            movement_date="2026-08-01",
            material_id=material["id"],
            movement_type="Compra",
            quantity=4,
            liters=76,
            unit_cost=100,
            total_cost=400,
            job_id=None,
            supplier="Proveedor enlazado",
            payment_mode="Pago parcial",
            amount_paid=100,
            notes="Compra enlazada",
        )
        debts = self.repo.list_debts("Materiales", "Proveedor enlazado")
        self.assertEqual(len(debts), 1)
        debt_id = int(debts[0]["id"])
        self.assertEqual(float(debts[0]["balance_due"]), 300)
        self.repo.add_debt_payment(debt_id, "2026-08-10", 125, "Abono desde deudas")
        movement = self.repo.get_material_movement(movement_id)
        debt = self.repo.get_debt(debt_id)
        self.assertEqual(float(movement["amount_paid"]), 225)
        self.assertEqual(float(debt["amount_paid"]), 225)
        self.assertEqual(float(debt["balance_due"]), 175)
        self.assertEqual(len(self.repo.purchase_payments(movement_id)), 2)

    def test_job_material_plan_is_created_and_editable(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 20)
        self.repo.ensure_job_material_plan(job_id, 25, 100)
        plan = self.repo.job_material_plan(job_id)
        self.assertEqual(len(plan), 2)
        self.assertEqual(sum(float(row["quantity"]) for row in plan if row["category"] == "Malla"), 1)
        self.assertEqual(sum(float(row["quantity"]) for row in plan if row["category"] == "Pintura"), 5)
        edited = [
            {
                "material_id": row["material_id"],
                "quantity": 2 if row["category"] == "Malla" else 4,
                "liters": 0 if row["category"] == "Malla" else 76,
                "notes": "Ajustado",
            }
            for row in plan
        ]
        self.repo.save_job_material_plan(job_id, edited)
        new_plan = self.repo.job_material_plan(job_id)
        self.assertEqual([float(row["quantity"]) for row in new_plan], [2, 4])

    def test_material_brand_is_saved(self) -> None:
        material = self.repo.list_materials()[1]
        movement_id = self.repo.record_material_movement(
            movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
            quantity=2, liters=38, unit_cost=90, total_cost=180, job_id=None,
            supplier="Proveedor Marca", brand="ImperMax", payment_mode="Pagado",
            amount_paid=180, notes="Lote inicial",
        )
        movement = self.repo.get_material_movement(movement_id)
        self.assertEqual(movement["brand"], "ImperMax")
        self.repo.update_material_movement(
            movement_id, movement_date="2026-08-02", material_id=material["id"],
            quantity=2, liters=38, unit_cost=95, total_cost=190, job_id=None,
            supplier="Proveedor Marca", brand="ImperMax Pro", target_paid=190, notes="Corregido",
        )
        self.assertEqual(self.repo.get_material_movement(movement_id)["brand"], "ImperMax Pro")

    def test_stock_aware_plan_can_mix_16_and_19_liters(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        paints = [row for row in self.repo.list_materials() if row["category"] == "Pintura"]
        paint19 = next(row for row in paints if float(row["package_size"]) == 19)
        paint16 = next(row for row in paints if float(row["package_size"]) == 16)
        for material, quantity in ((paint19, 2), (paint16, 2)):
            self.repo.record_material_movement(
                movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
                quantity=quantity, liters=quantity * float(material["package_size"]),
                unit_cost=50, total_cost=quantity * 50, job_id=None, supplier="Proveedor",
                brand="Marca", payment_mode="Pagado", amount_paid=quantity * 50, notes="",
            )
        self.repo.reset_job_material_plan(job_id, 25, 100)
        plan = [row for row in self.repo.job_material_plan(job_id) if row["category"] == "Pintura"]
        self.assertEqual(len(plan), 2)
        self.assertEqual(sum(float(row["quantity"]) for row in plan), 4)
        self.assertEqual({float(row["package_size"]) for row in plan}, {16.0, 19.0})

    def test_material_suggestion_is_available_before_saving_a_job(self) -> None:
        paints = [row for row in self.repo.list_materials() if row["category"] == "Pintura"]
        paint19 = next(row for row in paints if float(row["package_size"]) == 19)
        paint16 = next(row for row in paints if float(row["package_size"]) == 16)
        for material, quantity in ((paint19, 2), (paint16, 2)):
            self.repo.record_material_movement(
                movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
                quantity=quantity, liters=quantity * float(material["package_size"]),
                unit_cost=50, total_cost=quantity * 50, job_id=None, supplier="Proveedor",
                brand="Marca", payment_mode="Pagado", amount_paid=quantity * 50, notes="",
            )
        suggestion = self.repo.suggest_material_plan(100, 0, 25, 100)
        paint_rows = [row for row in suggestion if row["category"] == "Pintura"]
        self.assertEqual(sum(float(row["quantity"]) for row in paint_rows), 4)
        self.assertEqual({float(row["package_size"]) for row in paint_rows}, {16.0, 19.0})

    def test_job_material_liters_are_recalculated_from_quantity(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(50, 0)
        paint16 = next(
            row for row in self.repo.list_materials()
            if row["category"] == "Pintura" and float(row["package_size"]) == 16
        )
        self.repo.save_job_material_plan(
            job_id,
            [{
                "material_id": paint16["id"],
                "quantity": 2,
                # Simula el valor antiguo que quedaba visible al bajar de 3 a 2 cubetas.
                "liters": 48,
                "notes": "Corregido",
            }],
        )
        plan = self.repo.job_material_plan(job_id)
        self.assertEqual(len(plan), 1)
        self.assertEqual(float(plan[0]["quantity"]), 2)
        self.assertEqual(float(plan[0]["liters"]), 32)

    def test_pending_payroll_is_not_a_cost_until_job_is_completed(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        payroll = self.services.payroll.calculate_all(
            self.services.payroll.default_lines("Brigada 1"), 100, 0
        )
        expected_payroll = sum(line.final_pay for line in payroll)
        self.services.payroll.save(job_id, payroll)

        # La nómina puede estar calculada de antemano, pero mientras el trabajo
        # no esté completado no es un costo financiero ni un pago acumulado.
        snapshot = self.repo.dashboard_snapshot("2026-08", 90)
        self.assertEqual(snapshot.costs, 0)
        self.assertEqual(snapshot.profit, 0)
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
        self.assertEqual(summary["payroll"], 0)
        series = self.repo.financial_series("2026-08-01", "2026-08-31", "month")
        self.assertEqual(series[0]["expenses"], 0)
        self.assertTrue(all(float(row["pay"]) == 0 for row in self.repo.list_workers(False)))
        self.assertTrue(all(float(row["pay"]) == 0 for row in self.repo.worker_report()))

        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Finalizado",
            crew_id=self.repo.active_crews()[0]["id"],
            measurement_date="2026-08-01",
            start_date="2026-08-02",
            completion_date="2026-08-03",
            agreed_price=1000,
            notes="",
        )

        snapshot = self.repo.dashboard_snapshot("2026-08", 90)
        self.assertEqual(snapshot.costs, expected_payroll)
        self.assertEqual(snapshot.profit, -expected_payroll)
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
        self.assertEqual(summary["payroll"], expected_payroll)
        series = self.repo.financial_series("2026-08-01", "2026-08-31", "month")
        self.assertEqual(series[0]["expenses"], expected_payroll)

    def test_cash_flow_ignores_unpaid_credit_until_payment(self) -> None:
        self.repo.save_settings({"cash_opening_balance": 500})
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        self.repo.add_payment(job_id, "2026-08-05", "Cobro", 1000, "")
        material = self.repo.list_materials()[1]
        movement_id = self.repo.record_material_movement(
            movement_date="2026-08-06", material_id=material["id"], movement_type="Compra",
            quantity=4, liters=76, unit_cost=100, total_cost=400, job_id=None,
            supplier="Proveedor crédito", brand="Marca", payment_mode="Pendiente",
            amount_paid=0, notes="Compra completamente a crédito",
        )

        # La compra aumenta inventario y deuda, pero todavía no salió dinero.
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
        self.assertEqual(summary["material_purchases"], 400)
        self.assertEqual(summary["material_payments"], 0)
        self.assertEqual(summary["expenses"], 0)
        self.assertEqual(summary["profit"], 1000)
        self.assertEqual(summary["cash_balance"], 1500)

        self.repo.add_purchase_payment(movement_id, "2026-08-10", 150, "Abono real")
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
        self.assertEqual(summary["material_payments"], 150)
        self.assertEqual(summary["expenses"], 150)
        self.assertEqual(summary["profit"], 850)
        self.assertEqual(summary["cash_balance"], 1350)
        series = self.repo.financial_series("2026-01-01", "2026-12-31", "month")
        august = next(row for row in series if row["period"] == "2026-08")
        self.assertEqual(august["income"], 1000)
        self.assertEqual(august["expenses"], 150)
        self.assertEqual(august["profit"], 850)

    def test_cash_flow_does_not_double_count_material_debt_payment(self) -> None:
        material = self.repo.list_materials()[1]
        movement_id = self.repo.record_material_movement(
            movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
            quantity=2, liters=38, unit_cost=100, total_cost=200, job_id=None,
            supplier="Proveedor", brand="Marca", payment_mode="Pendiente", amount_paid=0, notes="",
        )
        debt = self.repo.list_debts("Materiales", "Proveedor")[0]
        self.repo.add_debt_payment(int(debt["id"]), "2026-08-12", 50, "Pago desde deudas")
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
        self.assertEqual(summary["material_payments"], 50)
        self.assertEqual(summary["debt_payments"], 0)
        self.assertEqual(summary["expenses"], 50)
        self.assertEqual(self.repo.get_material_movement(movement_id)["amount_paid"], 50)

    def test_financial_summary_and_series(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        self.repo.add_payment(job_id, "2026-08-10", "Cobro", 1000, "")
        self.repo.add_expense("2026-08-11", "Transporte", 100, "Logística", job_id)
        material = self.repo.list_materials()[0]
        self.repo.record_material_movement(
            movement_date="2026-08-12", material_id=material["id"], movement_type="Compra",
            quantity=1, liters=0, unit_cost=200, total_cost=200, job_id=None,
            supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=200, notes="",
        )
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
        self.assertEqual(summary["income"], 1000)
        self.assertEqual(summary["general_expenses"], 100)
        self.assertEqual(summary["material_purchases"], 200)
        self.assertEqual(summary["profit"], 700)
        series = self.repo.financial_series("2026-01-01", "2026-12-31", "month")
        august = next(row for row in series if row["period"] == "2026-08")
        self.assertEqual(august["income"], 1000)
        self.assertEqual(august["expenses"], 300)

    def test_foreign_payment_is_income_without_increasing_cash(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        crew = self.repo.active_crews()[0]
        payroll = self.services.payroll.calculate_all(
            self.services.payroll.default_lines("Brigada 1"), 100, 0
        )
        self.services.payroll.save(job_id, payroll)
        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Finalizado",
            crew_id=crew["id"],
            measurement_date="2026-08-01",
            start_date="2026-08-02",
            completion_date="2026-08-03",
            agreed_price=1000,
            notes="",
        )
        cash_after_completion = self.repo.cash_balance()

        payment_id = self.repo.add_payment(
            job_id,
            "2026-08-03",
            "Pago final en el extranjero",
            1000,
            "Pago recibido fuera del país",
            affects_cash=False,
            tip_amount=125,
        )
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")

        self.assertEqual(payment_id, self.repo.payments(job_id)[0]["id"])
        self.assertAlmostEqual(summary["job_income"], 1125)
        self.assertAlmostEqual(summary["foreign_job_income"], 1125)
        self.assertAlmostEqual(summary["cash_job_income"], 0)
        self.assertAlmostEqual(summary["income"], 1125)
        self.assertAlmostEqual(summary["cash_inflows"], 0)
        self.assertAlmostEqual(summary["payroll"], 190)
        self.assertAlmostEqual(summary["profit"], -190)
        self.assertAlmostEqual(self.repo.cash_balance(), cash_after_completion)
        self.assertAlmostEqual(self.repo.job_payment_summary(job_id)["balance"], 0)
        ledger_row = next(row for row in self.repo.cash_ledger() if row["source_id"] == payment_id)
        self.assertAlmostEqual(ledger_row["amount"], 1125)
        self.assertFalse(ledger_row["affects_cash"])
        series = self.repo.financial_series("2026-08-01", "2026-08-31", "month")
        self.assertEqual(len(series), 1)
        self.assertAlmostEqual(series[0]["job_income"], 1125)
        self.assertAlmostEqual(series[0]["foreign_job_income"], 1125)
        self.assertAlmostEqual(series[0]["cash_job_income"], 0)
        self.assertAlmostEqual(series[0]["income"], 0)

    def test_legacy_foreign_payment_remains_visible_but_non_cash(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        payment_id = self.repo.db.execute(
            """INSERT INTO payments(
                payment_date, job_id, payment_type, amount, affects_cash, tip_amount, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            # Simulates the rows normalized incorrectly by the previous fix.
            ("2026-08-16", job_id, "Pago final en el extranjero", 400, 1, 0, "Histórico"),
        )

        # Opening the database runs the compatibility migration for old rows.
        migrated_repo = AppRepository(Database(self.db.path))
        row = migrated_repo.payments(job_id)[0]
        self.assertEqual(int(row["affects_cash"]), 0)
        ledger_row = next(item for item in migrated_repo.cash_ledger() if item["source_id"] == payment_id)
        self.assertAlmostEqual(ledger_row["amount"], 400)
        self.assertFalse(ledger_row["affects_cash"])

    def test_payment_can_be_edited_or_deleted_from_its_job(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        payment_id = self.repo.add_payment(
            job_id,
            "2026-08-10",
            "Pago final en el extranjero",
            400,
            "Cobro que se debe corregir",
        )
        self.repo.update_payment(
            payment_id,
            job_id,
            "2026-08-11",
            "Pago final",
            250,
            "Cobro corregido",
            tip_amount=25,
        )
        updated = self.repo.payment(payment_id, job_id)
        self.assertEqual(updated["payment_date"], "2026-08-11")
        self.assertEqual(updated["payment_type"], "Pago final")
        self.assertAlmostEqual(float(updated["amount"]), 275)
        self.assertAlmostEqual(float(updated["tip_amount"]), 25)
        self.assertAlmostEqual(self.repo.job_payment_summary(job_id)["paid"], 250)
        ledger_row = next(item for item in self.repo.cash_ledger() if item["source_id"] == payment_id)
        self.assertAlmostEqual(ledger_row["amount"], 275)

        self.repo.delete_payment(payment_id, job_id)
        self.assertIsNone(self.repo.payment(payment_id, job_id))
        self.assertFalse(any(item["source_id"] == payment_id for item in self.repo.cash_ledger()))
        self.assertAlmostEqual(self.repo.job_payment_summary(job_id)["paid"], 0)

    def test_tip_counts_as_income_and_cash_but_not_as_job_payment(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        payment_id = self.repo.add_payment(
            job_id,
            "2026-08-15",
            "Pago final",
            1000,
            "Propina voluntaria",
            tip_amount=75,
        )
        row = self.repo.payments(job_id)[0]
        summary = self.repo.financial_summary("2026-08-01", "2026-08-31")

        self.assertEqual(int(row["id"]), payment_id)
        self.assertAlmostEqual(float(row["amount"]), 1075)
        self.assertAlmostEqual(float(row["tip_amount"]), 75)
        self.assertAlmostEqual(self.repo.job_payment_summary(job_id)["paid"], 1000)
        self.assertAlmostEqual(self.repo.job_payment_summary(job_id)["balance"], 0)
        client = self.repo.list_clients("Cliente prueba")[0]
        self.assertAlmostEqual(float(client["balance"]), 0)
        self.assertAlmostEqual(summary["income"], 1075)
        self.assertAlmostEqual(summary["cash_inflows"], 1075)
        ledger_row = next(item for item in self.repo.cash_ledger() if item["source_id"] == payment_id)
        self.assertAlmostEqual(ledger_row["amount"], 1075)
        self.assertIn("Propina", ledger_row["notes"])

    def test_job_status_flow_and_automatic_start(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(80, 0)
        self._stock_all_materials(10)
        job = self.repo.get_job(job_id)
        self.assertEqual(job["status"], "Medido")
        self.assertEqual(job["measurement_date"], "2026-08-01")

        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Confirmado",
            crew_id=self.repo.active_crews()[0]["id"],
            measurement_date="2026-08-01",
            start_date="2099-08-10",
            agreed_price=800,
            notes="",
        )
        self.assertEqual(self.repo.get_job(job_id)["status"], "Confirmado")
        self.repo.advance_due_jobs("2099-08-09")
        self.assertEqual(self.repo.get_job(job_id)["status"], "Confirmado")
        self.repo.advance_due_jobs("2099-08-10")
        started = self.repo.get_job(job_id)
        self.assertEqual(started["status"], "En Progreso")
        self.assertEqual(int(started["materials_deducted"]), 1)
        self.assertGreater(self.repo.job_material_consumption_count(job_id), 0)

    def test_in_progress_start_date_can_be_corrected_without_rededucting_materials(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(80, 0)
        initial_stock = self._stock_all_materials(10)
        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Confirmado",
            crew_id=self.repo.active_crews()[0]["id"],
            measurement_date="2026-08-01",
            start_date="2099-08-10",
            agreed_price=800,
            notes="",
        )
        self.repo.advance_due_jobs("2099-08-10")
        running = self.repo.get_job(job_id)
        before_stock = {
            int(row["id"]): float(row["stock_quantity"])
            for row in self.repo.list_materials()
        }
        before_consumptions = self.repo.job_material_consumption_count(job_id)

        self.services.jobs.save_job(
            job_id=job_id,
            current_job=running,
            status="En Progreso",
            crew_id=running["crew_id"],
            measurement_date="2026-08-01",
            start_date="2099-08-08",
            agreed_price=800,
            notes="Fecha corregida",
        )

        corrected = self.repo.get_job(job_id)
        self.assertEqual(corrected["status"], "En Progreso")
        self.assertEqual(corrected["start_date"], "2099-08-08")
        self.assertEqual(
            {
                int(row["id"]): float(row["stock_quantity"])
                for row in self.repo.list_materials()
            },
            before_stock,
        )
        self.assertEqual(self.repo.job_material_consumption_count(job_id), before_consumptions)
        self.assertNotEqual(before_stock, initial_stock)

    def test_reprogramming_returns_materials_and_allows_new_start(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        initial_stock = self._stock_all_materials(10)
        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Confirmado",
            crew_id=self.repo.active_crews()[0]["id"],
            measurement_date="2026-08-01",
            start_date="2099-01-10",
            agreed_price=1000,
            notes="",
        )
        self.repo.advance_due_jobs("2099-01-10")
        running = self.repo.get_job(job_id)
        self.assertEqual(running["status"], "En Progreso")
        consumed_stock = {int(row["id"]): float(row["stock_quantity"]) for row in self.repo.list_materials()}
        self.assertTrue(any(consumed_stock[mid] < qty for mid, qty in initial_stock.items()))

        messages = self.services.jobs.save_job(
            job_id=job_id,
            current_job=running,
            status="Confirmado",
            crew_id=running["crew_id"],
            measurement_date="2026-08-01",
            start_date="2099-02-10",
            agreed_price=1000,
            notes="Reprogramado",
        )
        self.assertTrue(any(message.startswith("Devuelto:") for message in messages))
        rescheduled = self.repo.get_job(job_id)
        self.assertEqual(rescheduled["status"], "Confirmado")
        self.assertEqual(rescheduled["start_date"], "2099-02-10")
        self.assertEqual(int(rescheduled["materials_deducted"]), 0)
        restored_stock = {int(row["id"]): float(row["stock_quantity"]) for row in self.repo.list_materials()}
        self.assertEqual(restored_stock, initial_stock)
        movements = self.repo.material_movements(job_id)
        self.assertEqual(
            {row["movement_type"] for row in movements},
            {"Consumo", "Devolución"},
        )

        self.repo.advance_due_jobs("2099-02-10")
        restarted = self.repo.get_job(job_id)
        self.assertEqual(restarted["status"], "En Progreso")
        self.assertGreater(self.repo.job_material_consumption_count(job_id), 0)

    def test_due_job_without_stock_remains_confirmed(self) -> None:
        _client_id, _measurement_id, job_id = self._create_measurement_and_job(100, 0)
        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Confirmado",
            crew_id=self.repo.active_crews()[0]["id"],
            measurement_date="2026-08-01",
            start_date="2099-03-10",
            agreed_price=1000,
            notes="",
        )
        moved = self.repo.advance_due_jobs("2099-03-10")
        self.assertEqual(moved, 0)
        self.assertEqual(self.repo.get_job(job_id)["status"], "Confirmado")
        self.assertEqual(self.repo.job_material_consumption_count(job_id), 0)

    def test_finalization_sets_today_and_searches_partial_client_data(self) -> None:
        client_id, _measurement_id, job_id = self._create_measurement_and_job(55, 0)
        self.repo.save_client("Cliente Especial", "555-7788", "Avenida Central 123", client_id=client_id)
        job = self.repo.get_job(job_id)
        self.services.jobs.save_job(
            job_id=job_id,
            current_job=job,
            status="Finalizado",
            crew_id=self.repo.active_crews()[0]["id"],
            measurement_date="2026-08-01",
            start_date="2026-08-02",
            completion_date="2026-08-05",
            agreed_price=550,
            notes="",
        )
        finished = self.repo.get_job(job_id)
        self.assertEqual(finished["status"], "Finalizado")
        self.assertEqual(finished["completion_date"], "2026-08-05")
        self.assertEqual(finished["maintenance_due_date"], "2029-08-05")
        self.assertEqual(len(self.repo.list_jobs("Todos", 90, "Especial")), 1)
        self.assertEqual(len(self.repo.list_jobs("Todos", 90, "Central 12")), 1)
        self.assertEqual(len(self.repo.list_jobs("Todos", 90, "7788")), 1)


# Material reconciliation regression tests added in v0.6.3.
def _v063_test_real_consumption_returns_unused_stock(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job(36, 0)
    paint16 = next(
        row for row in self.repo.list_materials()
        if row["category"] == "Pintura" and float(row["package_size"]) == 16
    )
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=paint16["id"], movement_type="Compra",
        quantity=9, liters=144, unit_cost=78, total_cost=702, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=702, notes="",
    )
    self.repo.save_job_material_plan(job_id, [{
        "material_id": paint16["id"], "quantity": 2, "liters": 999, "notes": "Previsto"
    }])
    self.repo.auto_consume_job_materials(job_id, 25, 100, movement_date="2026-08-05")
    stock_after_start = next(row for row in self.repo.list_materials() if row["id"] == paint16["id"])
    self.assertAlmostEqual(float(stock_after_start["stock_quantity"]), 7.0)

    # El consumo final fue 1.7 cubetas, no 2.
    self.repo.save_job_material_plan(job_id, [{
        "material_id": paint16["id"], "quantity": 1.7, "liters": 48, "notes": "Real"
    }])
    messages = self.repo.reconcile_job_materials_to_plan(job_id, movement_date="2026-08-08")
    self.assertTrue(any(message.startswith("Devuelto:") for message in messages))
    plan = self.repo.job_material_plan(job_id)
    self.assertAlmostEqual(float(plan[0]["liters"]), 27.2)
    stock_final = next(row for row in self.repo.list_materials() if row["id"] == paint16["id"])
    self.assertAlmostEqual(float(stock_final["stock_quantity"]), 7.3)
    self.assertAlmostEqual(float(stock_final["stock_liters"]), 116.8)
    net = self.repo.job_material_net_usage(job_id)
    self.assertEqual(len(net), 1)
    self.assertAlmostEqual(float(net[0]["quantity"]), 1.7)
    self.assertAlmostEqual(float(net[0]["liters"]), 27.2)


def _v063_test_real_consumption_can_remove_extra_stock(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job(36, 0)
    paint16 = next(
        row for row in self.repo.list_materials()
        if row["category"] == "Pintura" and float(row["package_size"]) == 16
    )
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=paint16["id"], movement_type="Compra",
        quantity=9, liters=144, unit_cost=78, total_cost=702, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=702, notes="",
    )
    self.repo.save_job_material_plan(job_id, [{"material_id": paint16["id"], "quantity": 2, "notes": ""}])
    self.repo.auto_consume_job_materials(job_id, 25, 100)
    self.repo.save_job_material_plan(job_id, [{"material_id": paint16["id"], "quantity": 2.2, "notes": ""}])
    messages = self.repo.reconcile_job_materials_to_plan(job_id)
    self.assertTrue(any(message.startswith("Retirado:") for message in messages))
    stock = next(row for row in self.repo.list_materials() if row["id"] == paint16["id"])
    self.assertAlmostEqual(float(stock["stock_quantity"]), 6.8)
    self.assertAlmostEqual(float(self.repo.job_material_net_usage(job_id)[0]["quantity"]), 2.2)


def _v063_test_switching_paint_size_reconciles_each_material(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job(50, 0)
    paints = [row for row in self.repo.list_materials() if row["category"] == "Pintura"]
    paint16 = next(row for row in paints if float(row["package_size"]) == 16)
    paint19 = next(row for row in paints if float(row["package_size"]) == 19)
    for material in (paint16, paint19):
        self.repo.record_material_movement(
            movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
            quantity=5, liters=5 * float(material["package_size"]), unit_cost=50,
            total_cost=250, job_id=None, supplier="Proveedor", brand="Marca",
            payment_mode="Pagado", amount_paid=250, notes="",
        )
    self.repo.save_job_material_plan(job_id, [{"material_id": paint16["id"], "quantity": 2, "notes": ""}])
    self.repo.auto_consume_job_materials(job_id, 25, 100)
    self.repo.save_job_material_plan(job_id, [
        {"material_id": paint16["id"], "quantity": 1, "notes": ""},
        {"material_id": paint19["id"], "quantity": 1, "notes": ""},
    ])
    self.repo.reconcile_job_materials_to_plan(job_id)
    stock = {int(row["id"]): float(row["stock_quantity"]) for row in self.repo.list_materials()}
    self.assertAlmostEqual(stock[int(paint16["id"])], 4.0)
    self.assertAlmostEqual(stock[int(paint19["id"])], 4.0)
    net = {int(row["material_id"]): float(row["quantity"]) for row in self.repo.job_material_net_usage(job_id)}
    self.assertEqual(net, {int(paint19["id"]): 1.0, int(paint16["id"]): 1.0})


def _v063_test_repairs_legacy_in_progress_job_without_checkout(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job(36, 0)
    paint16 = next(
        row for row in self.repo.list_materials()
        if row["category"] == "Pintura" and float(row["package_size"]) == 16
    )
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=paint16["id"], movement_type="Compra",
        quantity=9, liters=144, unit_cost=78, total_cost=702, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=702, notes="",
    )
    self.repo.save_job_material_plan(job_id, [{"material_id": paint16["id"], "quantity": 2, "notes": ""}])
    # Simula un registro creado por una versión donde el estado cambió pero el stock no.
    self.repo.db.execute(
        "UPDATE jobs SET status='En Progreso', start_date='2026-08-05', materials_deducted=0 WHERE id=?",
        (job_id,),
    )
    repaired = self.repo.repair_in_progress_materials()
    self.assertGreaterEqual(repaired, 1)
    stock = next(row for row in self.repo.list_materials() if row["id"] == paint16["id"])
    self.assertAlmostEqual(float(stock["stock_quantity"]), 7.0)
    self.assertEqual(int(self.repo.get_job(job_id)["materials_deducted"]), 1)


# Attach the regression tests to the existing unittest class without changing
# the original test layout.
CoreFlowTests.test_v063_real_consumption_returns_unused_stock = _v063_test_real_consumption_returns_unused_stock
CoreFlowTests.test_v063_real_consumption_can_remove_extra_stock = _v063_test_real_consumption_can_remove_extra_stock
CoreFlowTests.test_v063_switching_paint_size_reconciles_each_material = _v063_test_switching_paint_size_reconciles_each_material
CoreFlowTests.test_v063_repairs_legacy_in_progress_job_without_checkout = _v063_test_repairs_legacy_in_progress_job_without_checkout


def _v063_test_partial_existing_consumption_does_not_skip_other_materials(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job(50, 0)
    materials = self.repo.list_materials()
    mesh = next(row for row in materials if row["category"] == "Malla")
    paint16 = next(row for row in materials if row["category"] == "Pintura" and float(row["package_size"]) == 16)
    for material in (mesh, paint16):
        qty = 10
        self.repo.record_material_movement(
            movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
            quantity=qty,
            liters=qty * float(material["package_size"]) if material["category"] == "Pintura" else 0,
            unit_cost=10, total_cost=100, job_id=None, supplier="P", brand="M",
            payment_mode="Pagado", amount_paid=100, notes="",
        )
    self.repo.save_job_material_plan(job_id, [
        {"material_id": mesh["id"], "quantity": 1, "notes": ""},
        {"material_id": paint16["id"], "quantity": 2, "notes": ""},
    ])
    # Simula una salida manual parcial previa: solo media malla.
    self.repo.record_material_movement(
        movement_date="2026-08-02", material_id=mesh["id"], movement_type="Consumo",
        quantity=0.5, liters=0, unit_cost=10, job_id=job_id, notes="Parcial",
    )
    self.repo.auto_consume_job_materials(job_id, 25, 100)
    net = {int(row["material_id"]): float(row["quantity"]) for row in self.repo.job_material_net_usage(job_id)}
    self.assertAlmostEqual(net[int(mesh["id"])], 1.0)
    self.assertAlmostEqual(net[int(paint16["id"])], 2.0)


def _v063_test_manual_active_job_movement_edit_updates_real_plan(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job(36, 0)
    paint16 = next(row for row in self.repo.list_materials() if row["category"] == "Pintura" and float(row["package_size"]) == 16)
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=paint16["id"], movement_type="Compra",
        quantity=9, liters=144, unit_cost=78, total_cost=702, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=702, notes="",
    )
    self.repo.save_job_material_plan(job_id, [{"material_id": paint16["id"], "quantity": 2, "notes": ""}])
    self.repo.db.execute("UPDATE jobs SET status='En Progreso', start_date='2026-08-05' WHERE id=?", (job_id,))
    self.repo.auto_consume_job_materials(job_id, 25, 100)
    movement = next(row for row in self.repo.material_movements(job_id) if row["movement_type"] == "Consumo")
    self.repo.update_material_movement(
        int(movement["id"]), movement_date="2026-08-05", material_id=int(paint16["id"]),
        quantity=1.7, liters=27.2, unit_cost=float(movement["unit_cost"]),
        total_cost=1.7 * float(movement["unit_cost"]), job_id=job_id,
        notes="Corregido desde Materiales", supplier="", brand="", target_paid=0,
    )
    plan = self.repo.job_material_plan(job_id)
    self.assertEqual(len(plan), 1)
    self.assertAlmostEqual(float(plan[0]["quantity"]), 1.7)
    self.assertAlmostEqual(float(plan[0]["liters"]), 27.2)


CoreFlowTests.test_v063_partial_existing_consumption_does_not_skip_other_materials = _v063_test_partial_existing_consumption_does_not_skip_other_materials
CoreFlowTests.test_v063_manual_active_job_movement_edit_updates_real_plan = _v063_test_manual_active_job_movement_edit_updates_real_plan



def _v065_test_manual_cash_entries_affect_cash_but_not_job_income(self: CoreFlowTests) -> None:
    self.repo.save_settings({"cash_opening_balance": 1000})
    self.repo.save_cash_movement("2026-08-10", "Entrada", "Aporte de otro negocio", 500, "Transferencia externa")
    self.repo.save_cash_movement("2026-08-11", "Entrada", "Regalo / aporte personal", 100, "Regalo de un amigo")
    self.repo.save_cash_movement("2026-08-12", "Salida", "Retiro personal", 50, "Retiro de caja")
    self.assertAlmostEqual(self.repo.cash_balance(), 1550.0)
    summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
    self.assertAlmostEqual(summary["income"], 0.0)
    self.assertAlmostEqual(summary["manual_inflows"], 600.0)
    self.assertAlmostEqual(summary["manual_outflows"], 50.0)
    self.assertAlmostEqual(summary["cash_inflows"], 600.0)
    self.assertAlmostEqual(summary["profit"], 550.0)


def _v065_test_loan_reduces_cash_and_partial_repayments_restore_it(self: CoreFlowTests) -> None:
    self.repo.save_settings({"cash_opening_balance": 1000})
    loan_id = self.repo.save_loan("Amigo", "2026-08-01", 400, "Préstamo personal")
    self.assertAlmostEqual(self.repo.cash_balance(), 600.0)
    self.repo.add_loan_repayment(loan_id, "2026-08-05", 125, "Primer abono")
    self.assertAlmostEqual(self.repo.cash_balance(), 725.0)
    loan = self.repo.get_loan(loan_id)
    self.assertAlmostEqual(float(loan["repaid"]), 125.0)
    self.assertAlmostEqual(float(loan["balance_due"]), 275.0)
    summary = self.repo.loan_summary()
    self.assertEqual(summary, {"total": 400.0, "repaid": 125.0, "pending": 275.0})


def _v065_test_loan_cash_flow_is_not_operating_income_or_expense(self: CoreFlowTests) -> None:
    self.repo.save_settings({"cash_opening_balance": 1000})
    loan_id = self.repo.save_loan("Persona", "2026-08-03", 300, "")
    self.repo.add_loan_repayment(loan_id, "2026-08-08", 100, "")
    summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
    self.assertAlmostEqual(summary["income"], 0.0)
    self.assertAlmostEqual(summary["business_outflows"], 0.0)
    self.assertAlmostEqual(summary["loans_issued"], 300.0)
    self.assertAlmostEqual(summary["loan_repayments"], 100.0)
    self.assertAlmostEqual(summary["profit"], -200.0)
    self.assertAlmostEqual(summary["operating_cash_net"], 0.0)
    series = self.repo.financial_series("2026-08-01", "2026-08-31", "month")
    self.assertEqual(len(series), 1)
    self.assertAlmostEqual(series[0]["income"], 100.0)
    self.assertAlmostEqual(series[0]["expenses"], 300.0)
    self.assertAlmostEqual(series[0]["profit"], -200.0)


def _v065_test_cash_ledger_exposes_manual_and_loan_history(self: CoreFlowTests) -> None:
    manual_id = self.repo.save_cash_movement("2026-08-02", "Entrada", "Otro", 75, "Entrada explicada")
    loan_id = self.repo.save_loan("Cliente préstamo", "2026-08-03", 200, "Ayuda")
    self.repo.add_loan_repayment(loan_id, "2026-08-04", 50, "Abono")
    ledger = self.repo.cash_ledger()
    self.assertTrue(any(row["source_type"] == "manual" and row["source_id"] == manual_id for row in ledger))
    self.assertTrue(any(row["source_type"] == "loan" and row["source_id"] == loan_id for row in ledger))
    self.assertTrue(any(row["source_type"] == "loan_payment" and row["concept"] == "Cobro de Cliente préstamo" for row in ledger))


CoreFlowTests.test_v065_manual_cash_entries_affect_cash_but_not_job_income = _v065_test_manual_cash_entries_affect_cash_but_not_job_income
CoreFlowTests.test_v065_loan_reduces_cash_and_partial_repayments_restore_it = _v065_test_loan_reduces_cash_and_partial_repayments_restore_it
CoreFlowTests.test_v065_loan_cash_flow_is_not_operating_income_or_expense = _v065_test_loan_cash_flow_is_not_operating_income_or_expense
CoreFlowTests.test_v065_cash_ledger_exposes_manual_and_loan_history = _v065_test_cash_ledger_exposes_manual_and_loan_history


if __name__ == "__main__":
    unittest.main()

# Inventory consistency regression tests added in v0.6.6.
def _v066_test_material_movement_liters_are_derived_at_repository_boundary(self: CoreFlowTests) -> None:
    paint19 = next(
        row for row in self.repo.list_materials()
        if row["category"] == "Pintura" and float(row["package_size"]) == 19
    )
    movement_id = self.repo.record_material_movement(
        movement_date="2026-08-12", material_id=paint19["id"], movement_type="Compra",
        quantity=28, liters=19,  # Simula el valor obsoleto que produjo el error real.
        unit_cost=73.75, total_cost=2065, job_id=None,
        supplier="Proveedor Demo", brand="Marca", payment_mode="Pendiente", amount_paid=0, notes="",
    )
    movement = self.repo.get_material_movement(movement_id)
    material = next(row for row in self.repo.list_materials() if row["id"] == paint19["id"])
    self.assertAlmostEqual(float(movement["liters"]), 532.0)
    self.assertAlmostEqual(float(material["stock_quantity"]), 28.0)
    self.assertAlmostEqual(float(material["stock_liters"]), 532.0)

    self.repo.update_material_movement(
        movement_id, movement_date="2026-08-12", material_id=paint19["id"],
        quantity=20, liters=1, unit_cost=73.75, total_cost=1475, job_id=None,
        supplier="Proveedor Demo", brand="Marca", target_paid=0, notes="Corregido",
    )
    movement = self.repo.get_material_movement(movement_id)
    material = next(row for row in self.repo.list_materials() if row["id"] == paint19["id"])
    self.assertAlmostEqual(float(movement["liters"]), 380.0)
    self.assertAlmostEqual(float(material["stock_quantity"]), 20.0)
    self.assertAlmostEqual(float(material["stock_liters"]), 380.0)


def _v066_test_database_open_repairs_legacy_liter_corruption(self: CoreFlowTests) -> None:
    paint16 = next(
        row for row in self.repo.list_materials()
        if row["category"] == "Pintura" and float(row["package_size"]) == 16
    )
    movement_id = self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=paint16["id"], movement_type="Compra",
        quantity=9, liters=144, unit_cost=78, total_cost=702, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=702, notes="",
    )
    # Corrompe el dato como lo hacían versiones anteriores: la cantidad cambia
    # pero los litros quedan con el valor previo.
    self.repo.db.execute("UPDATE material_movements SET liters=48 WHERE id=?", (movement_id,))
    self.repo.db.execute("UPDATE materials SET stock_liters=48 WHERE id=?", (paint16["id"],))

    # Reabrir la DB ejecuta la reparación idempotente de v0.6.6.
    repaired_repo = AppRepository(Database(self.db.path))
    movement = repaired_repo.get_material_movement(movement_id)
    material = next(row for row in repaired_repo.list_materials() if row["id"] == paint16["id"])
    self.assertAlmostEqual(float(movement["liters"]), 144.0)
    self.assertAlmostEqual(float(material["stock_quantity"]), 9.0)
    self.assertAlmostEqual(float(material["stock_liters"]), 144.0)


def _v066_test_due_job_starts_with_enough_buckets_even_if_legacy_liters_were_wrong(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job(362, 0)
    materials = self.repo.list_materials()
    mesh = next(row for row in materials if row["category"] == "Malla")
    paint19 = next(
        row for row in materials
        if row["category"] == "Pintura" and float(row["package_size"]) == 19
    )
    self.repo.record_material_movement(
        movement_date="2026-08-12", material_id=mesh["id"], movement_type="Compra",
        quantity=10, liters=0, unit_cost=111.1, total_cost=1111, job_id=None,
        supplier="Proveedor Demo", brand="Marca", payment_mode="Pendiente", amount_paid=0, notes="",
    )
    purchase_id = self.repo.record_material_movement(
        movement_date="2026-08-12", material_id=paint19["id"], movement_type="Compra",
        quantity=28, liters=532, unit_cost=73.75, total_cost=2065, job_id=None,
        supplier="Proveedor Demo", brand="Marca", payment_mode="Pendiente", amount_paid=0, notes="",
    )
    self.repo.save_job_material_plan(job_id, [
        {"material_id": mesh["id"], "quantity": 4, "notes": "Previsto"},
        {"material_id": paint19["id"], "quantity": 15, "notes": "Previsto"},
    ])
    # Fuerza el mismo estado persistido que tenía la base real antes de abrir
    # la aplicación el 14/08: Confirmado con fecha de inicio ya vencida.
    self.repo.db.execute(
        "UPDATE jobs SET status='Confirmado', crew_id=?, measurement_date='2026-07-25', "
        "start_date='2026-08-13', agreed_price=3620, materials_deducted=0 WHERE id=?",
        (self.repo.active_crews()[0]["id"], job_id),
    )
    # Simula el registro histórico exacto del problema y reabre la base para
    # activar la reparación antes de evaluar trabajos vencidos.
    self.repo.db.execute("UPDATE material_movements SET liters=19 WHERE id=?", (purchase_id,))
    self.repo.db.execute("UPDATE materials SET stock_liters=19 WHERE id=?", (paint19["id"],))
    repaired_repo = AppRepository(Database(self.db.path))
    moved = repaired_repo.advance_due_jobs("2026-08-14")
    self.assertEqual(moved, 1)
    started = repaired_repo.get_job(job_id)
    self.assertEqual(started["status"], "En Progreso")
    stock = {int(row["id"]): row for row in repaired_repo.list_materials()}
    self.assertAlmostEqual(float(stock[int(mesh["id"])]["stock_quantity"]), 6.0)
    self.assertAlmostEqual(float(stock[int(paint19["id"])]["stock_quantity"]), 13.0)
    self.assertAlmostEqual(float(stock[int(paint19["id"])]["stock_liters"]), 247.0)


CoreFlowTests.test_v066_material_movement_liters_are_derived_at_repository_boundary = _v066_test_material_movement_liters_are_derived_at_repository_boundary
CoreFlowTests.test_v066_database_open_repairs_legacy_liter_corruption = _v066_test_database_open_repairs_legacy_liter_corruption
CoreFlowTests.test_v066_due_job_starts_with_enough_buckets_even_if_legacy_liters_were_wrong = _v066_test_due_job_starts_with_enough_buckets_even_if_legacy_liters_were_wrong


def _v067_test_material_sale_updates_stock_cash_and_financials(self: CoreFlowTests) -> None:
    self.repo.save_settings({"cash_opening_balance": 10000})
    paint19 = next(
        row for row in self.repo.list_materials()
        if row["category"] == "Pintura" and float(row["package_size"]) == 19
    )
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=paint19["id"], movement_type="Compra",
        quantity=10, liters=190, unit_cost=20, total_cost=200, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=200, notes="Stock",
    )
    cash_before = self.repo.cash_balance()
    sale_id = self.repo.save_material_sale(
        sale_date="2026-08-14", customer="Cliente venta",
        items=[{"material_id": paint19["id"], "quantity": 2, "unit_price": 50}],
        notes="Venta de prueba",
    )
    stock = next(row for row in self.repo.list_materials() if row["id"] == paint19["id"])
    self.assertAlmostEqual(float(stock["stock_quantity"]), 8.0)
    self.assertAlmostEqual(float(stock["stock_liters"]), 152.0)
    self.assertAlmostEqual(self.repo.cash_balance(), cash_before + 100.0)
    summary = self.repo.financial_summary("2026-08-01", "2026-08-31")
    self.assertAlmostEqual(summary["material_sales"], 100.0)
    self.assertAlmostEqual(summary["income"], 100.0)
    self.assertAlmostEqual(summary["cash_inflows"], 100.0)
    self.assertEqual(self.repo.get_material_sale(sale_id)["customer"], "Cliente venta")
    ledger = [row for row in self.repo.cash_ledger() if row["source_type"] == "material_sale"]
    self.assertEqual(len(ledger), 1)
    self.assertAlmostEqual(float(ledger[0]["amount"]), 100.0)


def _v067_test_edit_and_delete_material_sale_reconciles_inventory_and_cash(self: CoreFlowTests) -> None:
    self.repo.save_settings({"cash_opening_balance": 10000})
    paint16 = next(
        row for row in self.repo.list_materials()
        if row["category"] == "Pintura" and float(row["package_size"]) == 16
    )
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=paint16["id"], movement_type="Compra",
        quantity=10, liters=160, unit_cost=30, total_cost=300, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pagado", amount_paid=300, notes="Stock",
    )
    cash_before = self.repo.cash_balance()
    sale_id = self.repo.save_material_sale(
        sale_date="2026-08-14", customer="A",
        items=[{"material_id": paint16["id"], "quantity": 2, "unit_price": 45}],
    )
    self.repo.save_material_sale(
        sale_id=sale_id, sale_date="2026-08-14", customer="A corregido",
        items=[{"material_id": paint16["id"], "quantity": 3.5, "unit_price": 50}],
        notes="Corregida",
    )
    stock = next(row for row in self.repo.list_materials() if row["id"] == paint16["id"])
    self.assertAlmostEqual(float(stock["stock_quantity"]), 6.5)
    self.assertAlmostEqual(float(stock["stock_liters"]), 104.0)
    self.assertAlmostEqual(self.repo.cash_balance(), cash_before + 175.0)
    sale = self.repo.get_material_sale(sale_id)
    self.assertAlmostEqual(float(sale["total_amount"]), 175.0)
    self.repo.delete_material_sale(sale_id)
    stock = next(row for row in self.repo.list_materials() if row["id"] == paint16["id"])
    self.assertAlmostEqual(float(stock["stock_quantity"]), 10.0)
    self.assertAlmostEqual(float(stock["stock_liters"]), 160.0)
    self.assertAlmostEqual(self.repo.cash_balance(), cash_before)


def _v067_test_material_sale_cannot_make_stock_negative_and_rolls_back(self: CoreFlowTests) -> None:
    mesh = next(row for row in self.repo.list_materials() if row["category"] == "Malla")
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=mesh["id"], movement_type="Compra",
        quantity=2, liters=0, unit_cost=100, total_cost=200, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pendiente", amount_paid=0, notes="Stock",
    )
    before_sales = len(self.repo.list_material_sales())
    with self.assertRaises(ValueError):
        self.repo.save_material_sale(
            sale_date="2026-08-14", customer="Cliente",
            items=[{"material_id": mesh["id"], "quantity": 3, "unit_price": 130}],
        )
    self.assertEqual(len(self.repo.list_material_sales()), before_sales)
    stock = next(row for row in self.repo.list_materials() if row["id"] == mesh["id"])
    self.assertAlmostEqual(float(stock["stock_quantity"]), 2.0)


CoreFlowTests.test_v067_material_sale_updates_stock_cash_and_financials = _v067_test_material_sale_updates_stock_cash_and_financials
CoreFlowTests.test_v067_edit_and_delete_material_sale_reconciles_inventory_and_cash = _v067_test_edit_and_delete_material_sale_reconciles_inventory_and_cash
CoreFlowTests.test_v067_material_sale_cannot_make_stock_negative_and_rolls_back = _v067_test_material_sale_cannot_make_stock_negative_and_rolls_back


def _v067_test_mixed_material_sale_and_monthly_series(self: CoreFlowTests) -> None:
    self.repo.save_settings({"cash_opening_balance": 5000})
    mats = self.repo.list_materials()
    mesh = next(row for row in mats if row["category"] == "Malla")
    paint19 = next(row for row in mats if row["category"] == "Pintura" and float(row["package_size"]) == 19)
    for material, qty, cost in ((mesh, 5, 100), (paint19, 8, 70)):
        self.repo.record_material_movement(
            movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
            quantity=qty, liters=qty * float(material["package_size"] or 0),
            unit_cost=cost, total_cost=qty * cost, job_id=None, supplier="Proveedor",
            brand="Marca", payment_mode="Pendiente", amount_paid=0, notes="Stock",
        )
    self.repo.save_material_sale(
        sale_date="2026-08-14", customer="Cliente mixto",
        items=[
            {"material_id": mesh["id"], "quantity": 1, "unit_price": 140},
            {"material_id": paint19["id"], "quantity": 2.5, "unit_price": 95},
        ],
    )
    stocks = {int(row["id"]): row for row in self.repo.list_materials()}
    self.assertAlmostEqual(float(stocks[int(mesh["id"])]["stock_quantity"]), 4.0)
    self.assertAlmostEqual(float(stocks[int(paint19["id"])]["stock_quantity"]), 5.5)
    self.assertAlmostEqual(float(stocks[int(paint19["id"])]["stock_liters"]), 104.5)
    series = self.repo.financial_series("2026-08-01", "2026-08-31", "month")
    self.assertEqual(len(series), 1)
    self.assertAlmostEqual(series[0]["material_sales"], 377.5)
    self.assertAlmostEqual(series[0]["income"], 377.5)


def _v067_test_zero_price_sale_is_rejected(self: CoreFlowTests) -> None:
    material = self.repo.list_materials()[0]
    self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
        quantity=1, liters=0, unit_cost=100, total_cost=100, job_id=None,
        supplier="Proveedor", brand="Marca", payment_mode="Pendiente", amount_paid=0, notes="",
    )
    with self.assertRaises(ValueError):
        self.repo.save_material_sale(
            sale_date="2026-08-14", customer="Cliente",
            items=[{"material_id": material["id"], "quantity": 1, "unit_price": 0}],
        )


CoreFlowTests.test_v067_mixed_material_sale_and_monthly_series = _v067_test_mixed_material_sale_and_monthly_series
CoreFlowTests.test_v067_zero_price_sale_is_rejected = _v067_test_zero_price_sale_is_rejected


# Caja edits the source row, so these regression tests assert that the linked
# totals remain correct after each edit/delete operation.
def _v068_test_expense_can_be_edited_and_deleted_from_its_source(self: CoreFlowTests) -> None:
    expense_id = self.repo.add_expense("2026-08-10", "Combustible", 250, "Transporte", None)
    self.assertAlmostEqual(self.repo.cash_balance(), -250.0)
    self.repo.save_expense("2026-08-11", "Gasolina", 325, "Transporte", None, expense_id)
    expense = self.repo.get_expense(expense_id)
    self.assertEqual(expense["description"], "Gasolina")
    self.assertAlmostEqual(float(expense["amount"]), 325.0)
    self.assertAlmostEqual(self.repo.cash_balance(), -325.0)
    self.repo.delete_expense(expense_id)
    self.assertIsNone(self.repo.get_expense(expense_id))
    self.assertAlmostEqual(self.repo.cash_balance(), 0.0)
    self.assertFalse(any(row["source_type"] == "expense" for row in self.repo.cash_ledger()))


def _v068_test_linked_cash_payments_edit_and_delete_without_desync(self: CoreFlowTests) -> None:
    _client_id, _measurement_id, job_id = self._create_measurement_and_job()
    income_id = self.repo.add_payment(job_id, "2026-08-10", "Anticipo", 100, "Inicial")
    self.repo.update_payment(income_id, job_id, "2026-08-11", "Pago parcial", 140, "Corregido")
    self.assertAlmostEqual(self.repo.cash_balance(), 140.0)
    self.repo.delete_payment(income_id, job_id)
    self.assertAlmostEqual(self.repo.cash_balance(), 0.0)

    manual_id = self.repo.save_cash_movement("2026-08-10", "Salida", "Ajuste", 20, "Caja")
    self.repo.delete_cash_movement(manual_id)
    self.assertAlmostEqual(self.repo.cash_balance(), 0.0)

    loan_id = self.repo.save_loan("Persona", "2026-08-01", 200, "")
    repayment_id = self.repo.add_loan_repayment(loan_id, "2026-08-05", 50, "Primer pago")
    self.repo.update_loan_repayment(repayment_id, "2026-08-06", 80, "Corregido")
    self.assertAlmostEqual(float(self.repo.get_loan(loan_id)["balance_due"]), 120.0)
    self.repo.delete_loan_repayment(repayment_id)
    self.assertAlmostEqual(float(self.repo.get_loan(loan_id)["balance_due"]), 200.0)
    self.repo.delete_loan(loan_id)
    self.assertIsNone(self.repo.get_loan(loan_id))
    self.assertAlmostEqual(self.repo.cash_balance(), 0.0)


def _v068_test_debt_and_purchase_payment_edits_keep_cash_and_balances_consistent(self: CoreFlowTests) -> None:
    debt_id = self.repo.save_debt(
        creditor="Proveedor externo", debt_date="2026-08-01", total_amount=300,
        amount_paid=0, debt_type="Proveedor", notes="",
    )
    self.repo.add_debt_payment(debt_id, "2026-08-03", 100, "Abono")
    debt_payment = self.repo.debt_payments(debt_id)[0]
    self.repo.update_debt_payment(int(debt_payment["id"]), "2026-08-04", 125, "Corregido")
    self.assertAlmostEqual(float(self.repo.get_debt(debt_id)["amount_paid"]), 125.0)
    self.assertAlmostEqual(self.repo.cash_balance(), -125.0)
    self.repo.delete_debt_payment(int(debt_payment["id"]))
    self.assertAlmostEqual(float(self.repo.get_debt(debt_id)["amount_paid"]), 0.0)

    material = self.repo.list_materials()[0]
    movement_id = self.repo.record_material_movement(
        movement_date="2026-08-01", material_id=material["id"], movement_type="Compra",
        quantity=4, liters=0, unit_cost=50, total_cost=200, job_id=None,
        supplier="Proveedor de materiales", brand="", payment_mode="Pendiente", amount_paid=0, notes="",
    )
    self.repo.add_purchase_payment(movement_id, "2026-08-05", 75, "Abono")
    purchase_payment = self.repo.purchase_payments(movement_id)[0]
    self.repo.update_purchase_payment(int(purchase_payment["id"]), "2026-08-06", 120, "Corregido")
    purchase = self.repo.get_material_movement(movement_id)
    self.assertAlmostEqual(float(purchase["amount_paid"]), 120.0)
    self.repo.delete_purchase_payment(int(purchase_payment["id"]))
    purchase = self.repo.get_material_movement(movement_id)
    self.assertAlmostEqual(float(purchase["amount_paid"]), 0.0)
    self.assertAlmostEqual(self.repo.cash_balance(), 0.0)


CoreFlowTests.test_v068_expense_can_be_edited_and_deleted_from_its_source = _v068_test_expense_can_be_edited_and_deleted_from_its_source
CoreFlowTests.test_v068_linked_cash_payments_edit_and_delete_without_desync = _v068_test_linked_cash_payments_edit_and_delete_without_desync
CoreFlowTests.test_v068_debt_and_purchase_payment_edits_keep_cash_and_balances_consistent = _v068_test_debt_and_purchase_payment_edits_keep_cash_and_balances_consistent
