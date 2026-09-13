from __future__ import annotations

from dataclasses import dataclass
import math
from datetime import date, datetime
from calendar import monthrange
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .database import Database


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    cash_balance: float
    income: float
    costs: float
    profit: float
    completed_meters: float
    pending_jobs: int
    maintenance_count: int
    debt_balance: float
    debt_count: int


class AppRepository:
    """Centraliza todo el acceso SQL.

    Las páginas y diálogos no conocen sentencias SQL. Esto permite modificar
    SQLite, probar la lógica y evolucionar a otra base de datos sin reescribir
    la interfaz gráfica.
    """

    def __init__(self, db: Database) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Configuración e infraestructura
    # ------------------------------------------------------------------
    @property
    def database_path(self) -> Path:
        return self.db.path

    def setting(self, key: str, default: str = "") -> str:
        return self.db.get_setting(key, default)

    def setting_float(self, key: str, default: float) -> float:
        try:
            return float(self.setting(key, str(default)))
        except (TypeError, ValueError):
            return default

    def setting_int(self, key: str, default: int) -> int:
        try:
            return int(float(self.setting(key, str(default))))
        except (TypeError, ValueError):
            return default

    def save_settings(self, values: Mapping[str, Any]) -> None:
        with self.db.connection() as conn:
            conn.executemany(
                """
                INSERT INTO settings(key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                [(key, str(value)) for key, value in values.items()],
            )

    def backup(self, destination: Path | str) -> Path:
        return self.db.backup(destination)

    # ------------------------------------------------------------------
    # Dashboard / Finanzas (base de caja)
    # ------------------------------------------------------------------
    def _material_cash_payments(self, start_date: str, end_date: str) -> float:
        """Dinero realmente pagado por compras de materiales dentro del período.

        Las compras a crédito NO salen de caja hasta que existe un pago.  Para
        bases antiguas, donde ``amount_paid`` podía existir sin un movimiento
        detallado de pago, la diferencia se atribuye a la fecha de compra.
        """
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(amount),0) total FROM (
                SELECT mpp.payment_date tx_date, mpp.amount amount
                FROM material_purchase_payments mpp
                JOIN material_movements mm ON mm.id=mpp.movement_id
                WHERE mm.movement_type='Compra'
                UNION ALL
                SELECT mm.movement_date tx_date,
                       MAX(mm.amount_paid - COALESCE((
                           SELECT SUM(mpp2.amount) FROM material_purchase_payments mpp2
                           WHERE mpp2.movement_id=mm.id
                       ),0), 0) amount
                FROM material_movements mm
                WHERE mm.movement_type='Compra' AND mm.amount_paid>0.005
            ) x WHERE tx_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )
        return float(row["total"] or 0)

    def _other_debt_cash_payments(self, start_date: str, end_date: str) -> float:
        """Pagos reales de deudas que no provienen de una compra de material.

        Los pagos de deudas de materiales ya se reflejan en
        ``material_purchase_payments``; excluirlas aquí evita contabilizarlas
        dos veces.
        """
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(amount),0) total FROM (
                SELECT dp.payment_date tx_date, dp.amount amount
                FROM debt_payments dp
                JOIN debts d ON d.id=dp.debt_id
                WHERE d.material_movement_id IS NULL
                UNION ALL
                SELECT d.debt_date tx_date,
                       MAX(d.amount_paid - COALESCE((
                           SELECT SUM(dp2.amount) FROM debt_payments dp2
                           WHERE dp2.debt_id=d.id
                       ),0), 0) amount
                FROM debts d
                WHERE d.material_movement_id IS NULL AND d.amount_paid>0.005
            ) x WHERE tx_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )
        return float(row["total"] or 0)

    def _manual_cash_total(self, start_date: str, end_date: str, direction: str) -> float:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(amount),0) total FROM cash_movements
            WHERE direction=? AND movement_date BETWEEN ? AND ?""",
            (direction, start_date, end_date),
        )
        return float(row["total"] or 0)

    def _loan_repayments_total(self, start_date: str, end_date: str) -> float:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(amount),0) total FROM loan_repayments
            WHERE payment_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )
        return float(row["total"] or 0)

    def _job_payments_total(
        self,
        start_date: str,
        end_date: str,
        *,
        cash_only: bool = False,
    ) -> float:
        cash_clause = " AND COALESCE(affects_cash, 1)=1" if cash_only else ""
        row = self.db.fetchone(
            f"""SELECT COALESCE(SUM(amount),0) total FROM payments
            WHERE payment_date BETWEEN ? AND ?{cash_clause}""",
            (start_date, end_date),
        )
        return float(row["total"] or 0)

    def _foreign_job_payments_total(self, start_date: str, end_date: str) -> float:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(amount),0) total FROM payments
            WHERE payment_date BETWEEN ? AND ?
              AND payment_type LIKE '%extranjero%' COLLATE NOCASE""",
            (start_date, end_date),
        )
        return float(row["total"] or 0)

    def _material_sales_total(self, start_date: str, end_date: str) -> float:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(total_amount),0) total FROM material_sales
            WHERE sale_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )
        return float(row["total"] or 0)

    def _loans_issued_total(self, start_date: str, end_date: str) -> float:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(total_amount),0) total FROM loans_receivable
            WHERE loan_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )
        return float(row["total"] or 0)

    def cash_balance(self) -> float:
        """Efectivo real acumulado según los movimientos registrados.

        Fórmula: saldo inicial + cobros - gastos pagados - pagos de materiales
        - pagos de otras deudas - nómina de trabajos finalizados.

        Por regla del negocio, la nómina se considera pagada al finalizar el
        trabajo. Una compra a crédito aumenta la deuda, pero no reduce caja
        hasta que se registra un abono.
        """
        opening = self.setting_float("cash_opening_balance", 0.0)
        today_iso = date.today().isoformat()
        income = self._job_payments_total("0001-01-01", today_iso, cash_only=True)
        general = float(self.db.fetchone(
            "SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE expense_date<=?",
            (today_iso,),
        )["total"] or 0)
        materials_paid = self._material_cash_payments("0001-01-01", today_iso)
        other_debts_paid = self._other_debt_cash_payments("0001-01-01", today_iso)
        manual_in = self._manual_cash_total("0001-01-01", today_iso, "Entrada")
        manual_out = self._manual_cash_total("0001-01-01", today_iso, "Salida")
        loan_repayments = self._loan_repayments_total("0001-01-01", today_iso)
        material_sales = self._material_sales_total("0001-01-01", today_iso)
        loans_issued = self._loans_issued_total("0001-01-01", today_iso)
        payroll = float(self.db.fetchone(
            """SELECT COALESCE(SUM(jw.final_pay),0) total
            FROM job_workers jw JOIN jobs j ON j.id=jw.job_id
            WHERE j.status='Finalizado' AND j.completion_date IS NOT NULL
              AND date(j.completion_date)<=date(?)""",
            (today_iso,),
        )["total"] or 0)
        return round(
            opening + income + material_sales + manual_in + loan_repayments
            - general - materials_paid - other_debts_paid - payroll - loans_issued - manual_out,
            2,
        )

    def dashboard_snapshot(self, month: str, warning_days: int) -> DashboardSnapshot:
        self.advance_due_jobs()
        self.repair_in_progress_materials()
        year, month_number = (int(part) for part in month.split("-", 1))
        start_date = f"{year:04d}-{month_number:02d}-01"
        end_date = f"{year:04d}-{month_number:02d}-{monthrange(year, month_number)[1]:02d}"
        finance = self.financial_summary(start_date, end_date)
        completed_meters = float(
            self.db.fetchone(
                """SELECT COALESCE(SUM(new_area),0) total FROM jobs
                WHERE status='Finalizado' AND substr(completion_date,1,7)=?""",
                (month,),
            )["total"]
        )
        pending = int(
            self.db.fetchone(
                "SELECT COUNT(*) count FROM jobs WHERE status<>'Finalizado'"
            )["count"]
        )
        maintenance_count = int(
            self.db.fetchone(
                """SELECT COUNT(*) count FROM jobs
                WHERE status='Finalizado' AND maintenance_due_date IS NOT NULL
                AND maintenance_contacted=0
                AND date(maintenance_due_date) <= date('now', ?)""",
                (f"+{warning_days} day",),
            )["count"]
        )
        debt_row = self.db.fetchone(
            """SELECT COALESCE(SUM(MAX(total_amount-amount_paid,0)),0) balance,
            SUM(CASE WHEN total_amount-amount_paid>0.005 THEN 1 ELSE 0 END) count
            FROM debts"""
        )
        debt_balance = float(debt_row["balance"] or 0)
        debt_count = int(debt_row["count"] or 0)
        return DashboardSnapshot(
            cash_balance=float(finance["cash_balance"]),
            income=float(finance["income"]),
            costs=float(finance["expenses"]),
            profit=float(finance["profit"]),
            completed_meters=completed_meters,
            pending_jobs=pending,
            maintenance_count=maintenance_count,
            debt_balance=debt_balance,
            debt_count=debt_count,
        )

    def pending_debts(self, limit: int = 8) -> list[Any]:
        return self.db.fetchall(
            """SELECT d.id, d.creditor, d.debt_date, d.total_amount, d.amount_paid,
            MAX(d.total_amount-d.amount_paid,0) balance_due, d.debt_type,
            COALESCE(m.name, '') material, COALESCE(mm.brand, '') brand
            FROM debts d
            LEFT JOIN material_movements mm ON mm.id=d.material_movement_id
            LEFT JOIN materials m ON m.id=mm.material_id
            WHERE d.total_amount-d.amount_paid>0.005
            ORDER BY d.debt_date, d.id LIMIT ?""",
            (limit,),
        )

    def financial_summary(self, start_date: str, end_date: str) -> dict[str, float]:
        """Resumen financiero de caja para un período.

        ``expenses`` y ``profit`` se mantienen como nombres internos por
        compatibilidad, pero representan *salidas reales de efectivo* y *flujo
        neto de caja*. Una compra pendiente de pago solo aparece en
        ``material_purchases`` y en Deudas; no reduce el efectivo.
        """
        job_income = self._job_payments_total(start_date, end_date)
        cash_job_income = self._job_payments_total(start_date, end_date, cash_only=True)
        material_sales = self._material_sales_total(start_date, end_date)
        income = job_income + material_sales
        general_expenses = float(self.db.fetchone(
            "SELECT COALESCE(SUM(amount),0) total FROM expenses WHERE expense_date BETWEEN ? AND ?",
            (start_date, end_date),
        )["total"] or 0)
        material_purchases = float(self.db.fetchone(
            """SELECT COALESCE(SUM(total_cost),0) total FROM material_movements
            WHERE movement_type='Compra' AND movement_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )["total"] or 0)
        material_payments = self._material_cash_payments(start_date, end_date)
        debt_payments = self._other_debt_cash_payments(start_date, end_date)
        payroll = float(self.db.fetchone(
            """SELECT COALESCE(SUM(jw.final_pay),0) total
            FROM job_workers jw
            JOIN jobs j ON j.id=jw.job_id
            WHERE j.status='Finalizado'
              AND j.completion_date IS NOT NULL
              AND date(j.completion_date) BETWEEN date(?) AND date(?)""",
            (start_date, end_date),
        )["total"] or 0)
        manual_inflows = self._manual_cash_total(start_date, end_date, "Entrada")
        manual_outflows = self._manual_cash_total(start_date, end_date, "Salida")
        loan_repayments = self._loan_repayments_total(start_date, end_date)
        loans_issued = self._loans_issued_total(start_date, end_date)
        debt = self.debt_summary()
        inventory = self.inventory_financial_summary()
        loan_summary = self.loan_summary()

        business_outflows = general_expenses + material_payments + debt_payments + payroll
        cash_inflows = cash_job_income + material_sales + manual_inflows + loan_repayments
        cash_outflows = business_outflows + manual_outflows + loans_issued
        return {
            "cash_balance": self.cash_balance(),
            "cash_opening_balance": self.setting_float("cash_opening_balance", 0.0),
            "income": income,
            "job_income": job_income,
            "cash_job_income": cash_job_income,
            "foreign_job_income": self._foreign_job_payments_total(start_date, end_date),
            "material_sales": material_sales,
            "manual_inflows": manual_inflows,
            "loan_repayments": loan_repayments,
            "cash_inflows": cash_inflows,
            "general_expenses": general_expenses,
            "material_purchases": material_purchases,
            "material_payments": material_payments,
            "debt_payments": debt_payments,
            "payroll": payroll,
            "loans_issued": loans_issued,
            "manual_outflows": manual_outflows,
            "business_outflows": business_outflows,
            "expenses": cash_outflows,
            "profit": cash_inflows - cash_outflows,
            "operating_cash_net": cash_job_income + material_sales - business_outflows,
            "debt_balance": float(debt["pending"]),
            "loans_receivable_balance": float(loan_summary["pending"]),
            "inventory_value": float(inventory["stock_value"]),
        }

    def financial_series(self, start_date: str, end_date: str, grouping: str = "month") -> list[dict[str, Any]]:
        """Serie de flujo de caja: Entradas, Salidas y Neto.

        Incluye cobros de trabajos, entradas manuales y recuperaciones de
        préstamos; y como salidas los pagos operativos, préstamos entregados y
        salidas manuales. Las compras a crédito no salen de caja hasta pagarse.
        """
        key_len = 4 if grouping == "year" else 7

        def grouped_sql(sql: str, params: tuple[Any, ...]) -> dict[str, float]:
            rows = self.db.fetchall(sql, params)
            return {str(row["period"]): float(row["total"] or 0) for row in rows}

        job_income = grouped_sql(
            f"""SELECT substr(payment_date,1,{key_len}) period, COALESCE(SUM(amount),0) total
            FROM payments WHERE payment_date BETWEEN ? AND ?
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        cash_job_income = grouped_sql(
            f"""SELECT substr(payment_date,1,{key_len}) period, COALESCE(SUM(amount),0) total
            FROM payments WHERE payment_date BETWEEN ? AND ?
              AND COALESCE(affects_cash, 1)=1
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        foreign_job_income = grouped_sql(
            f"""SELECT substr(payment_date,1,{key_len}) period, COALESCE(SUM(amount),0) total
            FROM payments WHERE payment_date BETWEEN ? AND ?
              AND payment_type LIKE '%extranjero%' COLLATE NOCASE
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        material_sales = grouped_sql(
            f"""SELECT substr(sale_date,1,{key_len}) period, COALESCE(SUM(total_amount),0) total
            FROM material_sales WHERE sale_date BETWEEN ? AND ?
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        general = grouped_sql(
            f"""SELECT substr(expense_date,1,{key_len}) period, COALESCE(SUM(amount),0) total
            FROM expenses WHERE expense_date BETWEEN ? AND ?
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        manual_in = grouped_sql(
            f"""SELECT substr(movement_date,1,{key_len}) period, COALESCE(SUM(amount),0) total
            FROM cash_movements WHERE direction='Entrada' AND movement_date BETWEEN ? AND ?
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        manual_out = grouped_sql(
            f"""SELECT substr(movement_date,1,{key_len}) period, COALESCE(SUM(amount),0) total
            FROM cash_movements WHERE direction='Salida' AND movement_date BETWEEN ? AND ?
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        loan_repayments = grouped_sql(
            f"""SELECT substr(payment_date,1,{key_len}) period, COALESCE(SUM(amount),0) total
            FROM loan_repayments WHERE payment_date BETWEEN ? AND ?
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        loans_issued = grouped_sql(
            f"""SELECT substr(loan_date,1,{key_len}) period, COALESCE(SUM(total_amount),0) total
            FROM loans_receivable WHERE loan_date BETWEEN ? AND ?
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )
        material_rows = self.db.fetchall(
            """SELECT tx_date, amount FROM (
                SELECT mpp.payment_date tx_date, mpp.amount amount
                FROM material_purchase_payments mpp
                JOIN material_movements mm ON mm.id=mpp.movement_id
                WHERE mm.movement_type='Compra'
                UNION ALL
                SELECT mm.movement_date tx_date,
                       MAX(mm.amount_paid - COALESCE((
                           SELECT SUM(mpp2.amount) FROM material_purchase_payments mpp2
                           WHERE mpp2.movement_id=mm.id
                       ),0), 0) amount
                FROM material_movements mm
                WHERE mm.movement_type='Compra' AND mm.amount_paid>0.005
            ) x WHERE tx_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )
        debt_rows = self.db.fetchall(
            """SELECT tx_date, amount FROM (
                SELECT dp.payment_date tx_date, dp.amount amount
                FROM debt_payments dp JOIN debts d ON d.id=dp.debt_id
                WHERE d.material_movement_id IS NULL
                UNION ALL
                SELECT d.debt_date tx_date,
                       MAX(d.amount_paid - COALESCE((
                           SELECT SUM(dp2.amount) FROM debt_payments dp2
                           WHERE dp2.debt_id=d.id
                       ),0), 0) amount
                FROM debts d
                WHERE d.material_movement_id IS NULL AND d.amount_paid>0.005
            ) x WHERE tx_date BETWEEN ? AND ?""",
            (start_date, end_date),
        )

        def aggregate_rows(rows: Sequence[Any]) -> dict[str, float]:
            result: dict[str, float] = {}
            for row in rows:
                tx_date = str(row["tx_date"] or "")
                if not tx_date:
                    continue
                period = tx_date[:key_len]
                result[period] = result.get(period, 0.0) + float(row["amount"] or 0)
            return result

        materials = aggregate_rows(material_rows)
        debts_paid = aggregate_rows(debt_rows)
        payroll = grouped_sql(
            f"""SELECT substr(j.completion_date,1,{key_len}) period,
            COALESCE(SUM(jw.final_pay),0) total
            FROM job_workers jw JOIN jobs j ON j.id=jw.job_id
            WHERE j.status='Finalizado' AND j.completion_date IS NOT NULL
              AND date(j.completion_date) BETWEEN date(?) AND date(?)
            GROUP BY period ORDER BY period""",
            (start_date, end_date),
        )

        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        periods: list[str] = []
        if grouping == "year":
            periods = [str(year) for year in range(start.year, end.year + 1)]
        else:
            year, month = start.year, start.month
            while (year, month) <= (end.year, end.month):
                periods.append(f"{year:04d}-{month:02d}")
                month += 1
                if month == 13:
                    year += 1
                    month = 1

        result: list[dict[str, Any]] = []
        for period in periods:
            general_value = general.get(period, 0.0)
            material_value = materials.get(period, 0.0)
            debt_value = debts_paid.get(period, 0.0)
            payroll_value = payroll.get(period, 0.0)
            manual_in_value = manual_in.get(period, 0.0)
            manual_out_value = manual_out.get(period, 0.0)
            repayment_value = loan_repayments.get(period, 0.0)
            loans_issued_value = loans_issued.get(period, 0.0)
            reported_collected = job_income.get(period, 0.0)
            collected = cash_job_income.get(period, 0.0)
            sales_value = material_sales.get(period, 0.0)
            business_outflows = general_value + material_value + debt_value + payroll_value
            inflows = collected + sales_value + manual_in_value + repayment_value
            outflows = business_outflows + manual_out_value + loans_issued_value
            result.append({
                "period": period,
                # Compatibilidad con la gráfica existente: income/expenses son
                # entradas/salidas totales de efectivo para el período.
                "income": inflows,
                "expenses": outflows,
                "profit": inflows - outflows,
                "job_income": reported_collected,
                "cash_job_income": collected,
                "foreign_job_income": foreign_job_income.get(period, 0.0),
                "material_sales": sales_value,
                "manual_inflows": manual_in_value,
                "loan_repayments": repayment_value,
                "general_expenses": general_value,
                "material_payments": material_value,
                "debt_payments": debt_value,
                "payroll": payroll_value,
                "loans_issued": loans_issued_value,
                "manual_outflows": manual_out_value,
            })
        return result

    def expense_category_summary(self, start_date: str, end_date: str) -> list[Any]:
        return self.db.fetchall(
            """SELECT category, COALESCE(SUM(amount),0) total
            FROM expenses WHERE expense_date BETWEEN ? AND ?
            GROUP BY category ORDER BY total DESC""",
            (start_date, end_date),
        )

    def income_by_job(self, start_date: str, end_date: str, limit: int = 12) -> list[Any]:
        return self.db.fetchall(
            """SELECT clients.name client, jobs.code, COALESCE(SUM(payments.amount),0) total
            FROM payments JOIN jobs ON jobs.id=payments.job_id
            JOIN clients ON clients.id=jobs.client_id
            WHERE payments.payment_date BETWEEN ? AND ?
            GROUP BY jobs.id ORDER BY total DESC LIMIT ?""",
            (start_date, end_date, limit),
        )

    def maintenance_alerts(self, warning_days: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT jobs.id, jobs.code, jobs.completion_date, jobs.maintenance_due_date,
            clients.name, clients.phone
            FROM jobs JOIN clients ON clients.id=jobs.client_id
            WHERE jobs.status='Finalizado' AND jobs.maintenance_due_date IS NOT NULL
            AND jobs.maintenance_contacted=0
            AND date(jobs.maintenance_due_date) <= date('now', ?)
            ORDER BY jobs.maintenance_due_date""",
            (f"+{warning_days} day",),
        )

    def recent_jobs(self, limit: int = 10) -> list[Any]:
        return self.db.fetchall(
            """SELECT jobs.*, clients.name client, crews.name crew
            FROM jobs JOIN clients ON clients.id=jobs.client_id
            LEFT JOIN crews ON crews.id=jobs.crew_id
            ORDER BY jobs.id DESC LIMIT ?""",
            (limit,),
        )

    def crew_performance(self) -> list[Any]:
        return self.db.fetchall(
            """SELECT crews.name, COUNT(jobs.id) jobs_count,
            COALESCE(SUM(jobs.new_area),0) meters,
            COALESCE(SUM(jobs.agreed_price),0) amount
            FROM crews LEFT JOIN jobs
              ON jobs.crew_id=crews.id AND jobs.status='Finalizado'
            GROUP BY crews.id ORDER BY crews.id"""
        )

    # ------------------------------------------------------------------
    # Clientes
    # ------------------------------------------------------------------
    def list_clients(self, term: str = "") -> list[Any]:
        like = f"%{term.strip()}%"
        return self.db.fetchall(
            """SELECT clients.*,
            (SELECT COUNT(*) FROM measurements WHERE client_id=clients.id) measurements_count,
            (SELECT COUNT(*) FROM jobs WHERE client_id=clients.id) jobs_count,
            (SELECT MAX(completion_date) FROM jobs
             WHERE client_id=clients.id AND status='Finalizado') last_job,
            COALESCE((SELECT SUM(jobs.agreed_price) FROM jobs
                      WHERE client_id=clients.id),0)
            - COALESCE((SELECT SUM(MAX(payments.amount - COALESCE(payments.tip_amount, 0), 0)) FROM payments
                        JOIN jobs ON jobs.id=payments.job_id
                        WHERE jobs.client_id=clients.id),0) balance
            FROM clients
            WHERE clients.name LIKE ? OR clients.phone LIKE ? OR clients.address LIKE ?
            ORDER BY clients.name""",
            (like, like, like),
        )

    def client_work_rows(self, term: str = "") -> list[Any]:
        """One row per measured roof/work, repeating the client when needed."""
        like = f"%{term.strip()}%"
        return self.db.fetchall(
            """SELECT clients.id client_id, clients.name, clients.phone, clients.address,
            measurements.id measurement_id, jobs.id job_id,
            COALESCE(jobs.code, 'MED-' || printf('%04d', measurements.id)) work_code,
            measurements.measured_date,
            COALESCE(jobs.status, measurements.status) status,
            COALESCE(jobs.new_area, measurements.new_area) new_area,
            COALESCE(jobs.maintenance_area, measurements.maintenance_area) maintenance_area,
            COALESCE(jobs.agreed_price, measurements.final_price) amount,
            jobs.completion_date
            FROM measurements
            JOIN clients ON clients.id=measurements.client_id
            LEFT JOIN jobs ON jobs.measurement_id=measurements.id
            WHERE clients.name LIKE ? OR clients.phone LIKE ? OR clients.address LIKE ?
               OR COALESCE(jobs.code, '') LIKE ?
            ORDER BY clients.name, measurements.measured_date DESC, measurements.id DESC""",
            (like, like, like, like),
        )

    def clients_for_combo(self) -> list[Any]:
        return self.db.fetchall("SELECT id, name, phone FROM clients ORDER BY name")

    def get_client(self, client_id: int) -> Any | None:
        return self.db.fetchone("SELECT * FROM clients WHERE id=?", (client_id,))

    def save_client(
        self,
        name: str,
        phone: str = "",
        address: str = "",
        notes: str = "",
        client_id: int | None = None,
    ) -> int:
        if client_id:
            self.db.execute(
                "UPDATE clients SET name=?, phone=?, address=?, notes=? WHERE id=?",
                (name, phone, address, notes, client_id),
            )
            return client_id
        return self.db.execute(
            "INSERT INTO clients(name, phone, address, notes) VALUES (?, ?, ?, ?)",
            (name, phone, address, notes),
        )

    def client_related_count(self, client_id: int) -> int:
        row = self.db.fetchone(
            """SELECT
            (SELECT COUNT(*) FROM measurements WHERE client_id=?)
            + (SELECT COUNT(*) FROM jobs WHERE client_id=?) total""",
            (client_id, client_id),
        )
        return int(row["total"])

    def delete_client(self, client_id: int) -> None:
        self.db.execute("DELETE FROM clients WHERE id=?", (client_id,))

    # ------------------------------------------------------------------
    # Mediciones y presupuestos
    # ------------------------------------------------------------------
    def save_measurement(
        self,
        payload: Mapping[str, Any],
        lines: Sequence[Mapping[str, Any]],
        measurement_id: int | None = None,
    ) -> int:
        fields = (
            "client_id", "measured_date", "raw_text", "new_area",
            "maintenance_area", "total_area", "price_new",
            "price_maintenance", "masonry_extra", "membrane_extra",
            "manual_adjustment", "final_price", "status", "notes",
        )
        values = tuple(payload[field] for field in fields)
        with self.db.connection() as conn:
            if measurement_id:
                conn.execute(
                    """UPDATE measurements SET
                    client_id=?, measured_date=?, raw_text=?, new_area=?,
                    maintenance_area=?, total_area=?, price_new=?, price_maintenance=?,
                    masonry_extra=?, membrane_extra=?, manual_adjustment=?, final_price=?,
                    status=?, notes=? WHERE id=?""",
                    (*values, measurement_id),
                )
                conn.execute(
                    "DELETE FROM measurement_lines WHERE measurement_id=?",
                    (measurement_id,),
                )
                saved_id = measurement_id
            else:
                cur = conn.execute(
                    """INSERT INTO measurements(
                    client_id, measured_date, raw_text, new_area, maintenance_area,
                    total_area, price_new, price_maintenance, masonry_extra,
                    membrane_extra, manual_adjustment, final_price, status, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    values,
                )
                saved_id = int(cur.lastrowid)
            conn.executemany(
                """INSERT INTO measurement_lines(
                measurement_id, original_text, expression, result,
                work_type, section, observation
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        saved_id,
                        line["original_text"],
                        line["expression"],
                        line["result"],
                        line["work_type"],
                        line.get("section", "Techo"),
                        line.get("observation", ""),
                    )
                    for line in lines
                ],
            )
        return saved_id

    def get_measurement(self, measurement_id: int) -> Any | None:
        return self.db.fetchone("SELECT * FROM measurements WHERE id=?", (measurement_id,))

    def measurement_lines(self, measurement_id: int) -> list[Any]:
        return self.db.fetchall(
            "SELECT * FROM measurement_lines WHERE measurement_id=? ORDER BY id",
            (measurement_id,),
        )

    def measurements_for_client(self, client_id: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT measurements.*, clients.name client
            FROM measurements JOIN clients ON clients.id=measurements.client_id
            WHERE measurements.client_id=? ORDER BY measured_date DESC, measurements.id DESC""",
            (client_id,),
        )

    def all_measurements(self, limit: int = 250) -> list[Any]:
        return self.db.fetchall(
            """SELECT measurements.*, clients.name client
            FROM measurements JOIN clients ON clients.id=measurements.client_id
            ORDER BY measured_date DESC, measurements.id DESC LIMIT ?""",
            (limit,),
        )

    # ------------------------------------------------------------------
    # Trabajos
    # ------------------------------------------------------------------
    def active_crews(self) -> list[Any]:
        return self.db.fetchall("SELECT id, name FROM crews WHERE active=1 ORDER BY id")

    def jobs_for_combo(self) -> list[Any]:
        return self.db.fetchall(
            """SELECT jobs.id, jobs.code, clients.name client
            FROM jobs JOIN clients ON clients.id=jobs.client_id
            ORDER BY jobs.id DESC"""
        )

    def job_for_measurement(self, measurement_id: int) -> Any | None:
        return self.db.fetchone("SELECT * FROM jobs WHERE measurement_id=?", (measurement_id,))

    def upsert_job_from_measurement(
        self,
        *,
        measurement_id: int,
        client_id: int,
        status: str,
        new_area: float,
        maintenance_area: float,
        agreed_price: float,
        notes: str,
    ) -> int:
        existing = self.job_for_measurement(measurement_id)
        if existing:
            self.db.execute(
                """UPDATE jobs SET client_id=?, status=?, measurement_date=(
                    SELECT measured_date FROM measurements WHERE id=?
                ), new_area=?, maintenance_area=?, agreed_price=?, notes=? WHERE id=?""",
                (
                    client_id, status, measurement_id, new_area, maintenance_area,
                    agreed_price, notes, existing["id"],
                ),
            )
            return int(existing["id"])
        code = self.db.next_job_code()
        measurement = self.db.fetchone(
            "SELECT measured_date FROM measurements WHERE id=?", (measurement_id,)
        )
        measurement_date = (
            str(measurement["measured_date"])
            if measurement and measurement["measured_date"]
            else date.today().isoformat()
        )
        return self.db.execute(
            """INSERT INTO jobs(
            code, measurement_id, client_id, crew_id, status, measurement_date,
            new_area, maintenance_area, agreed_price, notes
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)""",
            (
                code, measurement_id, client_id, status, measurement_date,
                new_area, maintenance_area, agreed_price, notes,
            ),
        )

    def create_job_from_measurement(
        self,
        measurement_id: int,
        client_id: int,
        crew_id: int | None,
        new_area: float,
        maintenance_area: float,
        agreed_price: float,
        notes: str,
    ) -> int:
        job_id = self.upsert_job_from_measurement(
            measurement_id=measurement_id,
            client_id=client_id,
            status="Medido",
            new_area=new_area,
            maintenance_area=maintenance_area,
            agreed_price=agreed_price,
            notes=notes,
        )
        self.db.execute("UPDATE jobs SET crew_id=? WHERE id=?", (crew_id, job_id))
        return job_id

    def advance_due_jobs(self, today_iso: str | None = None) -> int:
        """Start due jobs and remove their planned materials from stock.

        A job is only promoted when its planned materials can be checked out.
        This prevents an ``En Progreso`` job from appearing while inventory
        still shows those materials as available.
        """
        effective_today = today_iso or date.today().isoformat()
        due_jobs = self.db.fetchall(
            """SELECT id, start_date FROM jobs
            WHERE status='Confirmado'
              AND start_date IS NOT NULL
              AND TRIM(start_date)<>''
              AND date(start_date) <= date(?)
            ORDER BY date(start_date), id""",
            (effective_today,),
        )
        moved = 0
        for row in due_jobs:
            job_id = int(row["id"])
            try:
                self.auto_consume_job_materials(
                    job_id,
                    self.setting_float("paint_coverage_m2", 25.0),
                    self.setting_float("mesh_roll_coverage_m2", 100.0),
                    movement_date=str(row["start_date"] or effective_today),
                )
            except ValueError:
                # Si no existe stock suficiente, el trabajo permanece
                # Confirmado para que el usuario corrija el inventario o el
                # plan de materiales antes de iniciarlo.
                continue
            with self.db.connection() as conn:
                cursor = conn.execute(
                    "UPDATE jobs SET status='En Progreso' WHERE id=? AND status='Confirmado'",
                    (job_id,),
                )
                if int(cursor.rowcount or 0):
                    conn.execute(
                        "UPDATE measurements SET status='En Progreso' "
                        "WHERE id=(SELECT measurement_id FROM jobs WHERE id=?)",
                        (job_id,),
                    )
                    moved += 1
        return moved

    def list_jobs(
        self,
        filter_name: str = "Todos",
        warning_days: int = 90,
        search_text: str = "",
    ) -> list[Any]:
        self.advance_due_jobs()
        self.repair_in_progress_materials()
        clauses: list[str] = []
        params: list[Any] = []
        if filter_name in ("Medido", "Confirmado", "En Progreso", "Finalizado"):
            clauses.append("jobs.status=?")
            params.append(filter_name)
        elif filter_name == "Mantenimiento sugerido":
            clauses.extend([
                "jobs.status='Finalizado'",
                "jobs.maintenance_contacted=0",
                "jobs.maintenance_due_date IS NOT NULL",
                "date(jobs.maintenance_due_date) <= date('now', ?)",
            ])
            params.append(f"+{warning_days} day")

        term = search_text.strip()
        if term:
            like = f"%{term}%"
            clauses.append(
                "(clients.name LIKE ? OR clients.address LIKE ? OR clients.phone LIKE ?)"
            )
            params.extend([like, like, like])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return self.db.fetchall(
            f"""SELECT jobs.*, clients.name client, clients.phone, clients.address,
            crews.name crew
            FROM jobs JOIN clients ON clients.id=jobs.client_id
            LEFT JOIN crews ON crews.id=jobs.crew_id
            {where}
            ORDER BY COALESCE(jobs.measurement_date, substr(jobs.created_at,1,10)) DESC,
                     jobs.id DESC""",
            tuple(params),
        )

    def active_jobs(self) -> list[Any]:
        """Jobs whose start date has arrived and are currently being executed."""
        self.advance_due_jobs()
        self.repair_in_progress_materials()
        return self.db.fetchall(
            """SELECT jobs.*, clients.name client, clients.phone, clients.address,
            crews.name crew,
            COALESCE((SELECT SUM(MAX(amount - COALESCE(tip_amount, 0), 0)) FROM payments WHERE payments.job_id=jobs.id),0) paid,
            MAX(jobs.agreed_price-
                COALESCE((SELECT SUM(MAX(amount - COALESCE(tip_amount, 0), 0)) FROM payments WHERE payments.job_id=jobs.id),0),0) balance
            FROM jobs JOIN clients ON clients.id=jobs.client_id
            LEFT JOIN crews ON crews.id=jobs.crew_id
            WHERE jobs.status='En Progreso'
            ORDER BY date(jobs.start_date), jobs.id"""
        )

    def get_job(self, job_id: int) -> Any | None:
        return self.db.fetchone(
            """SELECT jobs.*, clients.name client_name, clients.phone client_phone,
            clients.address client_address, crews.name crew_name
            FROM jobs JOIN clients ON clients.id=jobs.client_id
            LEFT JOIN crews ON crews.id=jobs.crew_id
            WHERE jobs.id=?""",
            (job_id,),
        )

    def delete_job(self, job_id: int) -> None:
        """Delete a job while preserving its measurement and inventory integrity."""
        with self.db.connection() as conn:
            job = conn.execute(
                "SELECT measurement_id FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if not job:
                raise ValueError("Trabajo no encontrado.")

            self._restore_job_materials_in_connection(
                conn,
                job_id,
                return_date=date.today().isoformat(),
                note_prefix="Devolución al almacén por eliminación del trabajo",
            )
            cursor = conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            if not int(cursor.rowcount or 0):
                raise ValueError("El trabajo ya no existe.")
            if job["measurement_id"]:
                conn.execute(
                    "UPDATE measurements SET status='Medido' WHERE id=?",
                    (job["measurement_id"],),
                )

    def update_job(self, job_id: int, values: Mapping[str, Any]) -> None:
        """Update a job and keep its client/measurement data consistent."""
        with self.db.connection() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise ValueError("Trabajo no encontrado.")
            conn.execute(
                """UPDATE jobs SET status=?, crew_id=?, measurement_date=?, start_date=?,
                completion_date=?, maintenance_due_date=?, new_area=?, maintenance_area=?,
                agreed_price=?, notes=? WHERE id=?""",
                (
                    values["status"], values.get("crew_id"), values.get("measurement_date"),
                    values.get("start_date"), values.get("completion_date"),
                    values.get("maintenance_due_date"), values.get("new_area", job["new_area"]),
                    values.get("maintenance_area", job["maintenance_area"]),
                    values["agreed_price"], values.get("notes", ""), job_id,
                ),
            )
            if "phone" in values or "address" in values:
                client = conn.execute("SELECT * FROM clients WHERE id=?", (job["client_id"],)).fetchone()
                conn.execute(
                    "UPDATE clients SET phone=?, address=? WHERE id=?",
                    (values.get("phone", client["phone"]), values.get("address", client["address"]), job["client_id"]),
                )
            measurement_id = job["measurement_id"]
            new_area = values.get("new_area", job["new_area"])
            maintenance_area = values.get("maintenance_area", job["maintenance_area"])
            if not measurement_id and "measurement_rows" in values:
                measurement_cursor = conn.execute(
                    """INSERT INTO measurements(
                    client_id, measured_date, raw_text, new_area, maintenance_area,
                    total_area, price_new, price_maintenance, final_price, status, notes
                    ) VALUES (?, ?, '', ?, ?, ?, 10, 6, ?, ?, ?)""",
                    (
                        job["client_id"], values.get("measurement_date") or date.today().isoformat(),
                        new_area, maintenance_area, float(new_area) + float(maintenance_area),
                        values["agreed_price"], values["status"], values.get("notes", ""),
                    ),
                )
                measurement_id = int(measurement_cursor.lastrowid)
                conn.execute(
                    "UPDATE jobs SET measurement_id=? WHERE id=?",
                    (measurement_id, job_id),
                )
            if measurement_id:
                conn.execute(
                    """UPDATE measurements SET new_area=?, maintenance_area=?, total_area=?,
                    final_price=?, status=?, notes=? WHERE id=?""",
                    (new_area, maintenance_area, float(new_area) + float(maintenance_area),
                     values["agreed_price"], values["status"], values.get("notes", ""), measurement_id),
                )
                if "measurement_rows" in values:
                    rows = values["measurement_rows"] or []
                    conn.execute(
                        "DELETE FROM measurement_lines WHERE measurement_id=?",
                        (measurement_id,),
                    )
                    conn.executemany(
                        """INSERT INTO measurement_lines(
                        measurement_id, original_text, expression, result,
                        work_type, section, observation
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        [
                            (
                                measurement_id,
                                str(line.get("original_text", "")).strip(),
                                str(line.get("expression", "")).strip(),
                                float(line.get("result", 0) or 0),
                                str(line.get("work_type", "Desde cero")).strip() or "Desde cero",
                                str(line.get("section", "Techo")).strip() or "Techo",
                                str(line.get("observation", "")).strip(),
                            )
                            for line in rows
                        ],
                    )

    def register_maintenance_contact(self, job_id: int, result: str) -> None:
        self.db.execute(
            """UPDATE jobs SET maintenance_contacted=1,
            maintenance_contact_date=?, maintenance_contact_result=? WHERE id=?""",
            (date.today().isoformat(), result, job_id),
        )

    # ------------------------------------------------------------------
    # Trabajadores y nómina
    # ------------------------------------------------------------------
    def list_workers(self, active_only: bool = False) -> list[Any]:
        where = "WHERE workers.active=1" if active_only else ""
        return self.db.fetchall(
            f"""SELECT workers.*, crews.name crew,
            COALESCE(SUM(CASE WHEN jobs.status='Finalizado'
              AND jw.counts_for_worker_meters=1 THEN jobs.new_area ELSE 0 END),0) meters,
            COALESCE(SUM(CASE WHEN jobs.status='Finalizado'
              THEN jw.final_pay ELSE 0 END),0) pay
            FROM workers LEFT JOIN crews ON crews.id=workers.base_crew_id
            LEFT JOIN job_workers jw ON jw.worker_id=workers.id
            LEFT JOIN jobs ON jobs.id=jw.job_id
            {where}
            GROUP BY workers.id ORDER BY workers.is_partner, workers.name"""
        )

    def workers_basic(self, active_only: bool = True) -> list[Any]:
        where = "WHERE active=1" if active_only else ""
        return self.db.fetchall(
            f"SELECT id, name, base_role, base_crew_id, is_partner, active FROM workers {where} ORDER BY name"
        )

    def get_worker(self, worker_id: int) -> Any | None:
        return self.db.fetchone("SELECT * FROM workers WHERE id=?", (worker_id,))

    def save_worker(self, values: Mapping[str, Any], worker_id: int | None = None) -> int:
        payload = (
            values["name"], values.get("base_crew_id"), values["base_role"],
            int(bool(values.get("is_partner"))), int(bool(values.get("active", True))),
        )
        if worker_id:
            self.db.execute(
                """UPDATE workers SET name=?, base_crew_id=?, base_role=?,
                is_partner=?, active=? WHERE id=?""",
                (*payload, worker_id),
            )
            return worker_id
        return self.db.execute(
            """INSERT INTO workers(name, base_crew_id, base_role, is_partner, active)
            VALUES (?, ?, ?, ?, ?)""",
            payload,
        )

    def job_payroll(self, job_id: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT jw.*, workers.name FROM job_workers jw
            JOIN workers ON workers.id=jw.worker_id
            WHERE jw.job_id=? ORDER BY jw.id""",
            (job_id,),
        )

    def clear_job_payroll(self, job_id: int) -> None:
        """Clear the paid amounts of a finalized job without losing its crew history."""
        with self.db.connection() as conn:
            job = conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise ValueError("El trabajo ya no existe.")
            conn.execute("UPDATE job_workers SET final_pay=0, paid=0 WHERE job_id=?", (job_id,))

    def replace_job_payroll(self, job_id: int, rows: Sequence[Mapping[str, Any]]) -> None:
        with self.db.connection() as conn:
            conn.execute("DELETE FROM job_workers WHERE job_id=?", (job_id,))
            conn.executemany(
                """INSERT INTO job_workers(
                job_id, worker_id, role, rate_new, rate_maintenance,
                base_pay, rounded_pay, manual_adjustment, adjustment_reason,
                final_pay, counts_for_worker_meters
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        job_id,
                        row["worker_id"],
                        row["role"],
                        row["rate_new"],
                        row["rate_maintenance"],
                        row["base_pay"],
                        row["rounded_pay"],
                        row["manual_adjustment"],
                        row.get("adjustment_reason", ""),
                        row["final_pay"],
                        int(bool(row.get("counts_for_worker_meters", True))),
                    )
                    for row in rows
                ],
            )

    # ------------------------------------------------------------------
    # Materiales
    # ------------------------------------------------------------------
    def list_materials(self, active_only: bool = True) -> list[Any]:
        where = "WHERE active=1" if active_only else ""
        return self.db.fetchall(f"SELECT * FROM materials {where} ORDER BY id")

    def inventory_financial_summary(self) -> dict[str, float]:
        stock_value = float(
            self.db.fetchone(
                "SELECT COALESCE(SUM(stock_quantity * average_unit_cost),0) total FROM materials WHERE active=1"
            )["total"]
        )
        payable = float(
            self.db.fetchone(
                """SELECT COALESCE(SUM(MAX(total_cost-amount_paid,0)),0) total
                FROM material_movements WHERE movement_type='Compra'"""
            )["total"]
        )
        paid = float(
            self.db.fetchone(
                """SELECT COALESCE(SUM(amount_paid),0) total
                FROM material_movements WHERE movement_type='Compra'"""
            )["total"]
        )
        return {"stock_value": stock_value, "payable": payable, "paid": paid}

    def material_movements(self, job_id: int | None = None, limit: int = 200) -> list[Any]:
        where = "WHERE mm.job_id=?" if job_id is not None else ""
        params: tuple[Any, ...] = (job_id,) if job_id is not None else (limit,)
        limit_sql = "" if job_id is not None else "LIMIT ?"
        return self.db.fetchall(
            f"""SELECT mm.*, materials.name material, materials.package_size,
            jobs.code job_code, mm.brand,
            CASE WHEN mm.movement_type='Compra' THEN MAX(mm.total_cost-mm.amount_paid,0) ELSE 0 END balance_due
            FROM material_movements mm
            JOIN materials ON materials.id=mm.material_id
            LEFT JOIN jobs ON jobs.id=mm.job_id
            {where} ORDER BY mm.id DESC {limit_sql}""",
            params,
        )

    def get_material_movement(self, movement_id: int) -> Any | None:
        return self.db.fetchone(
            """SELECT mm.*, materials.name material, materials.package_size, mm.brand,
            CASE WHEN mm.movement_type='Compra' THEN MAX(mm.total_cost-mm.amount_paid,0) ELSE 0 END balance_due
            FROM material_movements mm JOIN materials ON materials.id=mm.material_id
            WHERE mm.id=?""",
            (movement_id,),
        )

    # ------------------------------------------------------------------
    # Venta de materiales
    # ------------------------------------------------------------------
    def material_sales_summary(self) -> dict[str, float]:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(ms.total_amount),0) revenue,
            COALESCE(SUM((SELECT SUM(msi.quantity*msi.cost_unit) FROM material_sale_items msi WHERE msi.sale_id=ms.id)),0) cost
            FROM material_sales ms"""
        )
        revenue = float(row["revenue"] or 0)
        cost = float(row["cost"] or 0)
        return {"revenue": revenue, "cost": cost, "margin": revenue - cost}

    def list_material_sales(self, term: str = "") -> list[Any]:
        sql = """SELECT ms.*,
        COALESCE((SELECT SUM(msi.quantity*msi.cost_unit) FROM material_sale_items msi WHERE msi.sale_id=ms.id),0) cost,
        COALESCE((SELECT GROUP_CONCAT(m.name || ' × ' || printf('%.2f', msi.quantity), ', ')
                  FROM material_sale_items msi JOIN materials m ON m.id=msi.material_id
                  WHERE msi.sale_id=ms.id),'') detail
        FROM material_sales ms WHERE 1=1"""
        params: list[Any] = []
        term = term.strip()
        if term:
            sql += " AND (ms.customer LIKE ? OR ms.notes LIKE ? OR EXISTS(SELECT 1 FROM material_sale_items x JOIN materials m2 ON m2.id=x.material_id WHERE x.sale_id=ms.id AND m2.name LIKE ?))"
            like = f"%{term}%"
            params.extend([like, like, like])
        sql += " ORDER BY ms.sale_date DESC, ms.id DESC"
        return self.db.fetchall(sql, params)

    def get_material_sale(self, sale_id: int) -> Any | None:
        return self.db.fetchone("SELECT * FROM material_sales WHERE id=?", (sale_id,))

    def material_sale_items(self, sale_id: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT msi.*, m.name material, m.unit, m.package_size, m.category, m.stock_quantity
            FROM material_sale_items msi JOIN materials m ON m.id=msi.material_id
            WHERE msi.sale_id=? ORDER BY msi.id""",
            (sale_id,),
        )

    def save_material_sale(
        self,
        *,
        sale_date: str,
        customer: str,
        items: Sequence[Mapping[str, Any]],
        notes: str = "",
        sale_id: int | None = None,
    ) -> int:
        if not items:
            raise ValueError("Agrega al menos un material a la venta.")
        normalized: dict[int, dict[str, float]] = {}
        for item in items:
            material_id = int(item["material_id"])
            quantity = round(float(item["quantity"]), 4)
            unit_price = round(float(item["unit_price"]), 4)
            if quantity <= 0:
                raise ValueError("La cantidad vendida debe ser mayor que cero.")
            if unit_price <= 0:
                raise ValueError("El precio de venta por unidad debe ser mayor que cero.")
            if material_id in normalized:
                previous = normalized[material_id]
                combined_qty = previous["quantity"] + quantity
                combined_total = previous["quantity"] * previous["unit_price"] + quantity * unit_price
                previous["quantity"] = combined_qty
                previous["unit_price"] = combined_total / combined_qty
            else:
                normalized[material_id] = {"quantity": quantity, "unit_price": unit_price}

        with self.db.connection() as conn:
            old_material_ids: set[int] = set()
            if sale_id:
                existing = conn.execute("SELECT id FROM material_sales WHERE id=?", (sale_id,)).fetchone()
                if not existing:
                    raise ValueError("La venta ya no existe.")
                old_material_ids = {
                    int(row["material_id"]) for row in conn.execute(
                        "SELECT material_id FROM material_sale_items WHERE sale_id=?", (sale_id,)
                    ).fetchall()
                }
                conn.execute("DELETE FROM material_movements WHERE sale_id=? AND movement_type='Venta'", (sale_id,))
                conn.execute("DELETE FROM material_sale_items WHERE sale_id=?", (sale_id,))
                for material_id in old_material_ids:
                    self._recalculate_material_stock(conn, material_id)
            else:
                cur = conn.execute(
                    "INSERT INTO material_sales(sale_date, customer, total_amount, notes) VALUES (?, ?, 0, ?)",
                    (sale_date, customer.strip(), notes.strip()),
                )
                sale_id = int(cur.lastrowid)

            total_amount = 0.0
            affected = set(old_material_ids)
            for material_id, item in normalized.items():
                material = conn.execute(
                    "SELECT * FROM materials WHERE id=? AND active=1", (material_id,)
                ).fetchone()
                if not material:
                    raise ValueError("Uno de los materiales ya no existe o está inactivo.")
                available = float(material["stock_quantity"] or 0)
                quantity = float(item["quantity"])
                if quantity > available + 0.0001:
                    raise ValueError(
                        f"No hay suficiente {material['name']}. Disponible: {available:g} {material['unit']}(s); venta: {quantity:g}."
                    )
                unit_price = float(item["unit_price"])
                total_price = round(quantity * unit_price, 2)
                cost_unit = float(material["average_unit_cost"] or 0)
                conn.execute(
                    """INSERT INTO material_sale_items(sale_id, material_id, quantity, unit_price, cost_unit, total_price)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    (sale_id, material_id, quantity, unit_price, cost_unit, total_price),
                )
                liters = quantity * float(material["package_size"] or 0) if str(material["category"]) == "Pintura" else 0.0
                conn.execute(
                    """INSERT INTO material_movements(
                    movement_date, material_id, movement_type, quantity, liters, unit_cost, total_cost,
                    job_id, sale_id, supplier, brand, payment_status, amount_paid, notes
                    ) VALUES (?, ?, 'Venta', ?, ?, ?, ?, NULL, ?, '', '', 'No aplica', 0, ?)""",
                    (sale_date, material_id, quantity, liters, unit_price, total_price, sale_id, f"Venta de materiales · {customer.strip() or 'Cliente'}"),
                )
                total_amount += total_price
                affected.add(material_id)
                self._recalculate_material_stock(conn, material_id)

            conn.execute(
                "UPDATE material_sales SET sale_date=?, customer=?, total_amount=?, notes=? WHERE id=?",
                (sale_date, customer.strip(), round(total_amount, 2), notes.strip(), sale_id),
            )
            for material_id in affected:
                self._recalculate_material_stock(conn, material_id)
            return int(sale_id)

    def delete_material_sale(self, sale_id: int) -> None:
        with self.db.connection() as conn:
            exists = conn.execute("SELECT id FROM material_sales WHERE id=?", (sale_id,)).fetchone()
            if not exists:
                raise ValueError("La venta ya no existe.")
            material_ids = {
                int(row["material_id"]) for row in conn.execute(
                    "SELECT material_id FROM material_sale_items WHERE sale_id=?", (sale_id,)
                ).fetchall()
            }
            conn.execute("DELETE FROM material_movements WHERE sale_id=? AND movement_type='Venta'", (sale_id,))
            conn.execute("DELETE FROM material_sales WHERE id=?", (sale_id,))
            for material_id in material_ids:
                self._recalculate_material_stock(conn, material_id)

    @staticmethod
    def _payment_status(total: float, paid: float) -> str:
        if total <= 0 or paid >= total - 0.005:
            return "Pagado"
        if paid > 0:
            return "Pago parcial"
        return "Pendiente"

    @staticmethod
    def _recalculate_material_stock(conn: Any, material_id: int) -> None:
        material = conn.execute(
            "SELECT name, category, unit, package_size FROM materials WHERE id=?",
            (material_id,),
        ).fetchone()
        if not material:
            raise ValueError("Material no encontrado.")
        row = conn.execute(
            """SELECT
            COALESCE(SUM(CASE
                WHEN movement_type IN ('Compra','Devolución') THEN quantity
                WHEN movement_type IN ('Consumo','Venta') THEN -quantity
                ELSE 0 END),0) qty,
            COALESCE(SUM(CASE WHEN movement_type='Compra' THEN total_cost ELSE 0 END),0) purchase_value,
            COALESCE(SUM(CASE WHEN movement_type='Compra' THEN quantity ELSE 0 END),0) purchased_qty
            FROM material_movements WHERE material_id=?""",
            (material_id,),
        ).fetchone()
        qty = float(row["qty"] or 0)
        if qty < -0.001:
            raise ValueError(
                f"El movimiento dejaría {material['name']} con {qty:g} {material['unit']}(s). "
                "Revisa la cantidad disponible o los movimientos anteriores."
            )
        # Liters are derived from the number of buckets.  Never use the stored
        # movement liters as an independent stock constraint: historical builds
        # could leave that field stale after editing a quantity.
        liters = (
            max(qty, 0.0) * float(material["package_size"] or 0)
            if str(material["category"]) == "Pintura"
            else 0.0
        )
        purchased_qty = float(row["purchased_qty"] or 0)
        average = float(row["purchase_value"] or 0) / purchased_qty if purchased_qty > 0 else 0.0
        conn.execute(
            "UPDATE materials SET stock_quantity=?, stock_liters=?, average_unit_cost=? WHERE id=?",
            (max(qty, 0), liters, average, material_id),
        )

    @staticmethod
    def _sync_active_job_plan_from_net_usage(conn: Any, job_id: int | None) -> None:
        """Keep an active job's editable material table aligned with manual stock edits.

        The global Materiales page intentionally allows correcting a linked
        Consumo/Devolución movement.  For En Progreso/Finalizado jobs, those
        movements represent real usage, so the job material plan must follow
        the resulting net quantities instead of later overwriting the manual
        correction.
        """
        if not job_id:
            return
        job = conn.execute("SELECT status FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job or str(job["status"]) not in {"En Progreso", "Finalizado"}:
            return
        net_rows = conn.execute(
            """SELECT mm.material_id,
            COALESCE(SUM(CASE
                WHEN mm.movement_type='Consumo' THEN mm.quantity
                WHEN mm.movement_type='Devolución' THEN -mm.quantity
                ELSE 0 END),0) quantity
            FROM material_movements mm
            WHERE mm.job_id=? AND mm.movement_type IN ('Consumo','Devolución')
            GROUP BY mm.material_id""",
            (job_id,),
        ).fetchall()
        existing_notes = {
            int(row["material_id"]): str(row["notes"] or "")
            for row in conn.execute(
                "SELECT material_id, notes FROM job_material_plans WHERE job_id=?",
                (job_id,),
            ).fetchall()
        }
        conn.execute("DELETE FROM job_material_plans WHERE job_id=?", (job_id,))
        payload: list[tuple[Any, ...]] = []
        for row in net_rows:
            quantity = max(float(row["quantity"] or 0), 0.0)
            if quantity <= 0.0001:
                continue
            material = conn.execute(
                "SELECT category, package_size FROM materials WHERE id=?",
                (row["material_id"],),
            ).fetchone()
            if not material:
                continue
            liters = (
                quantity * float(material["package_size"] or 0)
                if str(material["category"]) == "Pintura"
                else 0.0
            )
            note = existing_notes.get(int(row["material_id"]), "") or "Ajustado desde movimientos de inventario"
            payload.append((job_id, int(row["material_id"]), quantity, liters, note))
        if payload:
            conn.executemany(
                """INSERT INTO job_material_plans(job_id, material_id, quantity, liters, notes)
                VALUES (?, ?, ?, ?, ?)""",
                payload,
            )
        conn.execute("UPDATE jobs SET materials_deducted=1 WHERE id=?", (job_id,))

    @staticmethod
    def _sync_debt_for_purchase(
        conn: Any,
        movement_id: int,
        *,
        payment_date: str | None = None,
        payment_delta: float = 0.0,
        payment_note: str = "",
    ) -> int | None:
        movement = conn.execute(
            "SELECT * FROM material_movements WHERE id=?", (movement_id,)
        ).fetchone()
        if not movement or movement["movement_type"] != "Compra":
            return None
        total = max(float(movement["total_cost"]), 0.0)
        paid = min(max(float(movement["amount_paid"]), 0.0), total)
        balance = max(total - paid, 0.0)
        creditor = (movement["supplier"] or "").strip() or "Proveedor sin especificar"
        debt = conn.execute(
            "SELECT * FROM debts WHERE material_movement_id=?", (movement_id,)
        ).fetchone()
        created = False
        if not debt and balance <= 0.005:
            return None
        if debt:
            debt_id = int(debt["id"])
            conn.execute(
                """UPDATE debts SET creditor=?, debt_date=?, total_amount=?, amount_paid=?,
                debt_type='Materiales' WHERE id=?""",
                (creditor, movement["movement_date"], total, paid, debt_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO debts(
                creditor, debt_date, total_amount, amount_paid, debt_type,
                material_movement_id, notes
                ) VALUES (?, ?, ?, ?, 'Materiales', ?, ?)""",
                (
                    creditor, movement["movement_date"], total, paid, movement_id,
                    "Generada automáticamente desde una compra de materiales",
                ),
            )
            debt_id = int(cur.lastrowid)
            created = True

        logged_amount = paid if created and paid > 0.005 else payment_delta
        if abs(logged_amount) > 0.005:
            conn.execute(
                """INSERT INTO debt_payments(
                debt_id, payment_date, amount, notes, source
                ) VALUES (?, ?, ?, ?, 'Materiales')""",
                (
                    debt_id,
                    payment_date or movement["movement_date"],
                    logged_amount,
                    payment_note or ("Pago inicial de la compra" if created else "Ajuste desde materiales"),
                ),
            )
        return debt_id

    def record_material_movement(
        self,
        *,
        movement_date: str,
        material_id: int,
        movement_type: str,
        quantity: float,
        liters: float,
        unit_cost: float,
        job_id: int | None,
        notes: str,
        total_cost: float | None = None,
        supplier: str = "",
        brand: str = "",
        payment_mode: str = "Pagado",
        amount_paid: float | None = None,
    ) -> int:
        quantity = float(quantity)
        if quantity < 0:
            raise ValueError("La cantidad del movimiento no puede ser negativa.")
        material_meta = self.db.fetchone(
            "SELECT category, package_size FROM materials WHERE id=? AND active=1",
            (material_id,),
        )
        if not material_meta:
            raise ValueError("Material no encontrado o inactivo.")
        # ``liters`` is intentionally ignored as an input for paint. It is a
        # derived value so repository callers cannot create an inconsistent
        # movement even if the UI sends a stale value.
        liters = (
            quantity * float(material_meta["package_size"] or 0)
            if str(material_meta["category"]) == "Pintura"
            else 0.0
        )
        total = round(quantity * unit_cost if total_cost is None else total_cost, 2)
        if movement_type == "Compra":
            paid = total if payment_mode == "Pagado" and amount_paid is None else float(amount_paid or 0)
            paid = min(max(paid, 0), total)
            status = self._payment_status(total, paid)
            effective_unit_cost = round(total / quantity, 4) if quantity > 0 else unit_cost
            if total - paid > 0.005 and not supplier.strip():
                raise ValueError("Indica la empresa o persona proveedora para registrar la deuda.")
        else:
            paid = 0.0
            status = "No aplica"
            effective_unit_cost = unit_cost
            total = round(quantity * unit_cost, 2)
        with self.db.connection() as conn:
            cur = conn.execute(
                """INSERT INTO material_movements(
                movement_date, material_id, movement_type, quantity, liters,
                unit_cost, total_cost, job_id, supplier, brand, payment_status, amount_paid, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    movement_date, material_id, movement_type, quantity, liters,
                    effective_unit_cost, total, job_id, supplier.strip(), brand.strip(), status, paid, notes,
                ),
            )
            movement_id = int(cur.lastrowid)
            if movement_type == "Compra" and abs(paid) > 0.005:
                conn.execute(
                    """INSERT INTO material_purchase_payments(movement_id, payment_date, amount, notes)
                    VALUES (?, ?, ?, ?)""",
                    (movement_id, movement_date, paid, "Pago registrado al crear la compra"),
                )
            if movement_type == "Compra":
                self._sync_debt_for_purchase(
                    conn,
                    movement_id,
                    payment_date=movement_date,
                    payment_note="Pago registrado al crear la compra",
                )
            self._recalculate_material_stock(conn, material_id)
            if movement_type in {"Consumo", "Devolución"} and job_id:
                self._sync_active_job_plan_from_net_usage(conn, int(job_id))
        return movement_id

    def update_material_movement(
        self,
        movement_id: int,
        *,
        movement_date: str,
        material_id: int,
        quantity: float,
        liters: float,
        unit_cost: float,
        total_cost: float,
        job_id: int | None,
        notes: str,
        supplier: str = "",
        brand: str = "",
        target_paid: float = 0.0,
    ) -> None:
        with self.db.connection() as conn:
            old = conn.execute("SELECT * FROM material_movements WHERE id=?", (movement_id,)).fetchone()
            if not old:
                raise ValueError("Movimiento no encontrado.")
            movement_type = old["movement_type"]
            quantity = float(quantity)
            if quantity < 0:
                raise ValueError("La cantidad del movimiento no puede ser negativa.")
            material_meta = conn.execute(
                "SELECT category, package_size FROM materials WHERE id=? AND active=1",
                (material_id,),
            ).fetchone()
            if not material_meta:
                raise ValueError("Material no encontrado o inactivo.")
            liters = (
                quantity * float(material_meta["package_size"] or 0)
                if str(material_meta["category"]) == "Pintura"
                else 0.0
            )
            total = round(total_cost if movement_type == "Compra" else quantity * unit_cost, 2)
            paid = min(max(target_paid, 0), total) if movement_type == "Compra" else 0.0
            status = self._payment_status(total, paid) if movement_type == "Compra" else "No aplica"
            effective_unit = round(total / quantity, 4) if movement_type == "Compra" and quantity > 0 else unit_cost
            if movement_type == "Compra" and total - paid > 0.005 and not supplier.strip():
                raise ValueError("Indica la empresa o persona proveedora para registrar la deuda.")
            old_paid = float(old["amount_paid"])
            conn.execute(
                """UPDATE material_movements SET movement_date=?, material_id=?, quantity=?, liters=?,
                unit_cost=?, total_cost=?, job_id=?, supplier=?, brand=?, payment_status=?, amount_paid=?, notes=?
                WHERE id=?""",
                (
                    movement_date, material_id, quantity, liters, effective_unit, total,
                    job_id, supplier.strip(), brand.strip(), status, paid, notes, movement_id,
                ),
            )
            delta = round(paid - old_paid, 2)
            if movement_type == "Compra" and abs(delta) > 0.005:
                conn.execute(
                    """INSERT INTO material_purchase_payments(movement_id, payment_date, amount, notes)
                    VALUES (?, ?, ?, ?)""",
                    (movement_id, movement_date, delta, "Ajuste manual del total pagado"),
                )
            if movement_type == "Compra":
                self._sync_debt_for_purchase(
                    conn,
                    movement_id,
                    payment_date=movement_date,
                    payment_delta=delta,
                    payment_note="Ajuste manual del total pagado en materiales",
                )
            affected = {int(old["material_id"]), int(material_id)}
            for affected_id in affected:
                self._recalculate_material_stock(conn, affected_id)
            if movement_type in {"Consumo", "Devolución"}:
                for linked_job_id in {old["job_id"], job_id}:
                    if linked_job_id:
                        self._sync_active_job_plan_from_net_usage(conn, int(linked_job_id))

    def add_purchase_payment(
        self, movement_id: int, payment_date: str, amount: float, notes: str = ""
    ) -> None:
        if amount <= 0:
            raise ValueError("El abono debe ser mayor que cero.")
        with self.db.connection() as conn:
            movement = conn.execute(
                "SELECT * FROM material_movements WHERE id=? AND movement_type='Compra'",
                (movement_id,),
            ).fetchone()
            if not movement:
                raise ValueError("Selecciona una compra válida.")
            balance = max(float(movement["total_cost"]) - float(movement["amount_paid"]), 0)
            if amount > balance + 0.005:
                raise ValueError(f"El abono supera el saldo pendiente de ${balance:,.2f}.")
            paid = round(float(movement["amount_paid"]) + amount, 2)
            status = self._payment_status(float(movement["total_cost"]), paid)
            conn.execute(
                "UPDATE material_movements SET amount_paid=?, payment_status=? WHERE id=?",
                (paid, status, movement_id),
            )
            conn.execute(
                """INSERT INTO material_purchase_payments(movement_id, payment_date, amount, notes)
                VALUES (?, ?, ?, ?)""",
                (movement_id, payment_date, amount, notes),
            )
            self._sync_debt_for_purchase(
                conn,
                movement_id,
                payment_date=payment_date,
                payment_delta=amount,
                payment_note=notes or "Abono registrado desde materiales",
            )

    def purchase_payments(self, movement_id: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT * FROM material_purchase_payments
            WHERE movement_id=? ORDER BY payment_date DESC, id DESC""",
            (movement_id,),
        )

    def get_purchase_payment(self, payment_id: int) -> Any | None:
        return self.db.fetchone(
            """SELECT mpp.*, mm.total_cost, mm.amount_paid, mm.movement_date,
            mm.supplier, m.name material
            FROM material_purchase_payments mpp
            JOIN material_movements mm ON mm.id=mpp.movement_id
            JOIN materials m ON m.id=mm.material_id
            WHERE mpp.id=?""",
            (payment_id,),
        )

    def update_purchase_payment(
        self, payment_id: int, payment_date: str, amount: float, notes: str = ""
    ) -> None:
        """Edit a material-payment entry and keep its purchase/debt totals aligned."""
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("El abono debe ser mayor que cero.")
        with self.db.connection() as conn:
            payment = conn.execute(
                "SELECT * FROM material_purchase_payments WHERE id=?", (payment_id,)
            ).fetchone()
            if not payment:
                raise ValueError("El abono de materiales ya no existe.")
            movement = conn.execute(
                "SELECT * FROM material_movements WHERE id=? AND movement_type='Compra'",
                (payment["movement_id"],),
            ).fetchone()
            if not movement:
                raise ValueError("La compra asociada al abono ya no existe.")
            adjusted_paid = round(
                float(movement["amount_paid"] or 0) - float(payment["amount"] or 0) + amount,
                2,
            )
            if adjusted_paid < -0.005 or adjusted_paid - float(movement["total_cost"] or 0) > 0.005:
                available = float(movement["total_cost"] or 0) - (
                    float(movement["amount_paid"] or 0) - float(payment["amount"] or 0)
                )
                raise ValueError(f"El abono no puede superar ${max(available, 0):,.2f}.")
            adjusted_paid = max(adjusted_paid, 0.0)
            delta = round(amount - float(payment["amount"] or 0), 2)
            conn.execute(
                "UPDATE material_purchase_payments SET payment_date=?, amount=?, notes=? WHERE id=?",
                (payment_date, amount, notes.strip(), payment_id),
            )
            conn.execute(
                "UPDATE material_movements SET amount_paid=?, payment_status=? WHERE id=?",
                (
                    adjusted_paid,
                    self._payment_status(float(movement["total_cost"] or 0), adjusted_paid),
                    movement["id"],
                ),
            )
            self._sync_debt_for_purchase(
                conn,
                int(movement["id"]),
                payment_date=payment_date,
                payment_delta=delta,
                payment_note="Corrección de abono desde Caja",
            )

    def delete_purchase_payment(self, payment_id: int) -> None:
        with self.db.connection() as conn:
            payment = conn.execute(
                "SELECT * FROM material_purchase_payments WHERE id=?", (payment_id,)
            ).fetchone()
            if not payment:
                raise ValueError("El abono de materiales ya no existe.")
            movement = conn.execute(
                "SELECT * FROM material_movements WHERE id=? AND movement_type='Compra'",
                (payment["movement_id"],),
            ).fetchone()
            if not movement:
                raise ValueError("La compra asociada al abono ya no existe.")
            adjusted_paid = max(round(float(movement["amount_paid"] or 0) - float(payment["amount"] or 0), 2), 0.0)
            conn.execute("DELETE FROM material_purchase_payments WHERE id=?", (payment_id,))
            conn.execute(
                "UPDATE material_movements SET amount_paid=?, payment_status=? WHERE id=?",
                (
                    adjusted_paid,
                    self._payment_status(float(movement["total_cost"] or 0), adjusted_paid),
                    movement["id"],
                ),
            )
            self._sync_debt_for_purchase(
                conn,
                int(movement["id"]),
                payment_date=str(payment["payment_date"]),
                payment_delta=-float(payment["amount"] or 0),
                payment_note="Abono eliminado desde Caja",
            )

    def clear_purchase_legacy_payment(self, movement_id: int) -> None:
        """Remove only the initial/legacy cash part of a material purchase.

        Detailed payments are preserved.  The ledger calls this the ``Pago
        inicial`` row, which is the difference between the purchase's paid
        total and its detailed payment rows.
        """
        with self.db.connection() as conn:
            movement = conn.execute(
                "SELECT * FROM material_movements WHERE id=? AND movement_type='Compra'", (movement_id,)
            ).fetchone()
            if not movement:
                raise ValueError("La compra ya no existe.")
            detailed = conn.execute(
                "SELECT COALESCE(SUM(amount),0) total FROM material_purchase_payments WHERE movement_id=?",
                (movement_id,),
            ).fetchone()
            paid = max(float(detailed["total"] or 0), 0.0)
            old_paid = float(movement["amount_paid"] or 0)
            delta = round(paid - old_paid, 2)
            if abs(delta) <= 0.005:
                raise ValueError("Esta compra no tiene un pago inicial independiente que eliminar.")
            conn.execute(
                "UPDATE material_movements SET amount_paid=?, payment_status=? WHERE id=?",
                (paid, self._payment_status(float(movement["total_cost"] or 0), paid), movement_id),
            )
            self._sync_debt_for_purchase(
                conn,
                movement_id,
                payment_date=str(movement["movement_date"]),
                payment_delta=delta,
                payment_note="Pago inicial eliminado desde Caja",
            )

    def job_material_consumption_count(self, job_id: int) -> int:
        row = self.db.fetchone(
            "SELECT COUNT(*) count FROM material_movements WHERE job_id=? AND movement_type='Consumo'",
            (job_id,),
        )
        return int(row["count"])

    @staticmethod
    def _suggest_material_plan_rows(
        conn: Any,
        new_area: float,
        maintenance_area: float,
        paint_coverage: float,
        mesh_coverage: float,
    ) -> list[dict[str, Any]]:
        """Return a stock-aware material suggestion without saving it.

        Keeping this calculation independent from a job record allows the
        Nueva medición screen to show and edit the exact plan before the first
        save.  The same helper is also used when a job needs a default plan, so
        both screens always follow identical rules.
        """
        new_area = max(float(new_area), 0.0)
        maintenance_area = max(float(maintenance_area), 0.0)
        total_area = new_area + maintenance_area
        suggestions: list[dict[str, Any]] = []

        if new_area > 0:
            mesh = conn.execute(
                "SELECT * FROM materials WHERE active=1 AND category='Malla' "
                "ORDER BY stock_quantity DESC, id LIMIT 1"
            ).fetchone()
            if mesh:
                quantity = float(math.ceil(new_area / max(mesh_coverage, 1)))
                available = float(mesh["stock_quantity"])
                shortage = max(quantity - available, 0.0)
                note = f"Sugerido según stock actual: {available:g} rollo(s) disponible(s)"
                if shortage > 0.001:
                    note += f" · Faltan {shortage:g} rollo(s)"
                suggestions.append({
                    "material_id": int(mesh["id"]),
                    "material": str(mesh["name"]),
                    "category": str(mesh["category"]),
                    "unit": str(mesh["unit"]),
                    "package_size": float(mesh["package_size"]),
                    "average_unit_cost": float(mesh["average_unit_cost"]),
                    "stock_quantity": available,
                    "quantity": quantity,
                    "liters": 0.0,
                    "notes": note,
                })

        if total_area > 0:
            buckets_needed = int(math.ceil(total_area / max(paint_coverage, 1)))
            paints = conn.execute(
                """SELECT * FROM materials WHERE active=1 AND category='Pintura'
                ORDER BY package_size DESC, id"""
            ).fetchall()
            remaining = buckets_needed
            allocations: list[list[Any]] = []
            for paint in paints:
                if remaining <= 0:
                    break
                available = max(int(math.floor(float(paint["stock_quantity"]) + 0.0001)), 0)
                take = min(remaining, available)
                if take > 0:
                    allocations.append([paint, take, False])
                    remaining -= take
            if remaining > 0 and paints:
                preferred = paints[0]
                existing = next(
                    (entry for entry in allocations if int(entry[0]["id"]) == int(preferred["id"])),
                    None,
                )
                if existing:
                    existing[1] += remaining
                    existing[2] = True
                else:
                    allocations.append([preferred, remaining, True])

            for paint, quantity_int, shortage in allocations:
                quantity = float(quantity_int)
                available = float(paint["stock_quantity"])
                note = f"Sugerido según stock: {available:g} cubeta(s) disponible(s)"
                if shortage or quantity > available + 0.001:
                    note += f" · Faltan {max(quantity - available, 0):g} cubeta(s)"
                suggestions.append({
                    "material_id": int(paint["id"]),
                    "material": str(paint["name"]),
                    "category": str(paint["category"]),
                    "unit": str(paint["unit"]),
                    "package_size": float(paint["package_size"]),
                    "average_unit_cost": float(paint["average_unit_cost"]),
                    "stock_quantity": available,
                    "quantity": quantity,
                    "liters": quantity * float(paint["package_size"]),
                    "notes": note,
                })
        return suggestions

    def suggest_material_plan(
        self,
        new_area: float,
        maintenance_area: float,
        paint_coverage: float,
        mesh_coverage: float,
    ) -> list[dict[str, Any]]:
        with self.db.connection() as conn:
            return self._suggest_material_plan_rows(
                conn, new_area, maintenance_area, paint_coverage, mesh_coverage
            )

    @staticmethod
    def _create_default_material_plan(
        conn: Any,
        job_id: int,
        paint_coverage: float,
        mesh_coverage: float,
        *,
        replace: bool = False,
        new_area_override: float | None = None,
        maintenance_area_override: float | None = None,
    ) -> None:
        """Create a stock-aware plan and allow mixing 16 L and 19 L paint."""
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise ValueError("Trabajo no encontrado.")
        if replace:
            conn.execute("DELETE FROM job_material_plans WHERE job_id=?", (job_id,))
        else:
            count = conn.execute(
                "SELECT COUNT(*) count FROM job_material_plans WHERE job_id=?", (job_id,)
            ).fetchone()["count"]
            if int(count):
                return
        new_area = float(job["new_area"] if new_area_override is None else new_area_override)
        maintenance_area = float(
            job["maintenance_area"] if maintenance_area_override is None else maintenance_area_override
        )
        suggestions = AppRepository._suggest_material_plan_rows(
            conn, new_area, maintenance_area, paint_coverage, mesh_coverage
        )
        rows = [
            (
                job_id,
                int(row["material_id"]),
                float(row["quantity"]),
                float(row["liters"]),
                str(row["notes"]),
            )
            for row in suggestions
        ]

        conn.executemany(
            """INSERT INTO job_material_plans(job_id, material_id, quantity, liters, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_id, material_id) DO UPDATE SET
            quantity=excluded.quantity, liters=excluded.liters, notes=excluded.notes""",
            rows,
        )

    def ensure_job_material_plan(self, job_id: int, paint_coverage: float, mesh_coverage: float) -> None:
        with self.db.connection() as conn:
            self._create_default_material_plan(conn, job_id, paint_coverage, mesh_coverage)

    def reset_job_material_plan(
        self,
        job_id: int,
        paint_coverage: float,
        mesh_coverage: float,
        *,
        new_area: float | None = None,
        maintenance_area: float | None = None,
    ) -> None:
        with self.db.connection() as conn:
            self._create_default_material_plan(
                conn, job_id, paint_coverage, mesh_coverage, replace=True,
                new_area_override=new_area, maintenance_area_override=maintenance_area,
            )

    def job_material_plan(self, job_id: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT jmp.*, materials.name material, materials.category,
            materials.unit, materials.package_size, materials.average_unit_cost,
            (jmp.quantity * materials.average_unit_cost) estimated_cost
            FROM job_material_plans jmp
            JOIN materials ON materials.id=jmp.material_id
            WHERE jmp.job_id=? ORDER BY materials.category, materials.package_size DESC""",
            (job_id,),
        )

    def save_job_material_plan(self, job_id: int, rows: Sequence[Mapping[str, Any]]) -> None:
        with self.db.connection() as conn:
            conn.execute("DELETE FROM job_material_plans WHERE job_id=?", (job_id,))
            payload = []
            for row in rows:
                quantity = float(row.get("quantity", 0))
                if quantity < 0:
                    raise ValueError("Las cantidades previstas no pueden ser negativas.")
                if quantity <= 0.0001:
                    continue
                material_id = int(row["material_id"])
                material = conn.execute(
                    "SELECT category, package_size FROM materials WHERE id=? AND active=1",
                    (material_id,),
                ).fetchone()
                if not material:
                    raise ValueError("Uno de los materiales seleccionados ya no está disponible.")
                # Los litros son un dato derivado. Recalcularlos aquí evita
                # inconsistencias aunque la celda de la interfaz todavía no
                # haya perdido el foco al pulsar Guardar.
                liters = (
                    quantity * float(material["package_size"])
                    if str(material["category"]) == "Pintura"
                    else 0.0
                )
                payload.append(
                    (job_id, material_id, quantity, liters, str(row.get("notes", "")))
                )
            conn.executemany(
                """INSERT INTO job_material_plans(job_id, material_id, quantity, liters, notes)
                VALUES (?, ?, ?, ?, ?)""",
                payload,
            )

    def job_material_net_usage(self, job_id: int) -> list[Any]:
        """Return the net quantity currently checked out from stock for a job.

        ``Consumo`` rows remove stock and ``Devolución`` rows return it.  The
        result is grouped by material so the UI can show the real amount still
        assigned to the job even when there have been several adjustments.
        """
        return self.db.fetchall(
            """SELECT materials.id material_id, materials.name material,
            materials.category, materials.unit, materials.package_size,
            materials.stock_quantity,
            COALESCE(SUM(CASE
                WHEN mm.movement_type='Consumo' THEN mm.quantity
                WHEN mm.movement_type='Devolución' THEN -mm.quantity
                ELSE 0 END),0) quantity,
            COALESCE(SUM(CASE
                WHEN mm.movement_type='Consumo' THEN mm.liters
                WHEN mm.movement_type='Devolución' THEN -mm.liters
                ELSE 0 END),0) liters
            FROM materials
            JOIN material_movements mm ON mm.material_id=materials.id
            WHERE mm.job_id=? AND mm.movement_type IN ('Consumo','Devolución')
            GROUP BY materials.id, materials.name, materials.category,
                     materials.unit, materials.package_size, materials.stock_quantity
            HAVING ABS(quantity) > 0.0001 OR ABS(liters) > 0.0001
            ORDER BY materials.category, materials.package_size DESC""",
            (job_id,),
        )

    def reconcile_job_materials_to_plan(
        self,
        job_id: int,
        *,
        movement_date: str | None = None,
        note_prefix: str = "Ajuste de consumo real",
    ) -> list[str]:
        """Make stock movements match the material plan exactly.

        Before a job starts, ``job_material_plans`` is the estimate.  Once the
        job is in progress the same editable rows become the real consumption
        target.  If the real amount is lower than what was checked out at the
        start, the difference is returned to stock.  If it is higher, only the
        extra amount is removed.  This also handles changing from 16 L paint to
        19 L paint without losing the audit trail.
        """
        with self.db.connection() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise ValueError("Trabajo no encontrado.")

            plan_rows = conn.execute(
                """SELECT jmp.material_id, jmp.quantity, materials.name,
                materials.category, materials.unit, materials.package_size,
                materials.stock_quantity, materials.average_unit_cost
                FROM job_material_plans jmp
                JOIN materials ON materials.id=jmp.material_id
                WHERE jmp.job_id=? AND jmp.quantity>0""",
                (job_id,),
            ).fetchall()
            desired = {int(row["material_id"]): float(row["quantity"]) for row in plan_rows}
            material_rows = {int(row["material_id"]): row for row in plan_rows}

            current_rows = conn.execute(
                """SELECT mm.material_id,
                COALESCE(SUM(CASE
                    WHEN mm.movement_type='Consumo' THEN mm.quantity
                    WHEN mm.movement_type='Devolución' THEN -mm.quantity
                    ELSE 0 END),0) quantity
                FROM material_movements mm
                WHERE mm.job_id=? AND mm.movement_type IN ('Consumo','Devolución')
                GROUP BY mm.material_id""",
                (job_id,),
            ).fetchall()
            current = {int(row["material_id"]): float(row["quantity"] or 0) for row in current_rows}

            # Materials removed from the plan still need to be returned, so
            # load their metadata as well.
            all_ids = set(desired) | set(current)
            missing_ids = [mid for mid in all_ids if mid not in material_rows]
            if missing_ids:
                placeholders = ",".join("?" for _ in missing_ids)
                for row in conn.execute(
                    f"""SELECT id material_id, name, category, unit, package_size,
                    stock_quantity, average_unit_cost FROM materials
                    WHERE id IN ({placeholders})""",
                    tuple(missing_ids),
                ).fetchall():
                    material_rows[int(row["material_id"])] = row

            # Validate all additional withdrawals before changing anything so
            # a failure never leaves half of the materials adjusted.
            for material_id in all_ids:
                delta = desired.get(material_id, 0.0) - current.get(material_id, 0.0)
                if delta <= 0.0001:
                    continue
                material = material_rows.get(material_id)
                if not material:
                    raise ValueError("Uno de los materiales del trabajo ya no existe.")
                available = float(material["stock_quantity"] or 0)
                if available + 0.001 < delta:
                    raise ValueError(
                        f"{material['name']} insuficiente: necesitas retirar {delta:g} "
                        f"{material['unit']}(s) adicionales y hay {available:g}."
                    )

            effective_date = movement_date or date.today().isoformat()
            messages: list[str] = []
            for material_id in sorted(all_ids):
                target = desired.get(material_id, 0.0)
                actual = current.get(material_id, 0.0)
                delta = target - actual
                if abs(delta) <= 0.0001:
                    continue
                material = material_rows[material_id]
                qty = abs(delta)
                package_size = float(material["package_size"] or 0)
                liters = qty * package_size if str(material["category"]) == "Pintura" else 0.0
                unit_cost = float(material["average_unit_cost"] or 0)
                total_cost = round(qty * unit_cost, 2)
                if delta > 0:
                    movement_type = "Consumo"
                    note = f"{note_prefix}: salida adicional del almacén"
                    verb = "Retirado"
                else:
                    movement_type = "Devolución"
                    note = f"{note_prefix}: material no utilizado devuelto al almacén"
                    verb = "Devuelto"
                conn.execute(
                    """INSERT INTO material_movements(
                    movement_date, material_id, movement_type, quantity, liters,
                    unit_cost, total_cost, job_id, supplier, payment_status,
                    amount_paid, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, '', 'No aplica', 0, ?)""",
                    (
                        effective_date, material_id, movement_type, qty, liters,
                        unit_cost, total_cost, job_id, note,
                    ),
                )
                self._recalculate_material_stock(conn, material_id)
                messages.append(
                    f"{verb}: {qty:g} {material['unit']}(s) de {material['name']}"
                )

            conn.execute("UPDATE jobs SET materials_deducted=1 WHERE id=?", (job_id,))
            return messages

    def ensure_in_progress_materials(self, job_id: int) -> list[str]:
        """Repair old/inconsistent in-progress jobs that never checked out stock."""
        job = self.db.fetchone("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job or str(job["status"]) != "En Progreso":
            return []
        self.ensure_job_material_plan(
            job_id,
            self.setting_float("paint_coverage_m2", 25.0),
            self.setting_float("mesh_roll_coverage_m2", 100.0),
        )
        return self.reconcile_job_materials_to_plan(
            job_id,
            movement_date=str(job["start_date"] or date.today().isoformat()),
            note_prefix="Regularización de materiales al iniciar el trabajo",
        )

    def repair_in_progress_materials(self) -> int:
        """Backfill stock checkout for jobs already marked En Progreso.

        Versions prior to 0.6.2 could leave an in-progress job without a stock
        movement.  This routine repairs those records when enough stock exists.
        """
        rows = self.db.fetchall(
            """SELECT id FROM jobs WHERE status='En Progreso' ORDER BY id"""
        )
        repaired = 0
        for row in rows:
            job_id = int(row["id"])
            before = self.db.fetchone(
                """SELECT COALESCE(SUM(CASE
                    WHEN movement_type='Consumo' THEN quantity
                    WHEN movement_type='Devolución' THEN -quantity
                    ELSE 0 END),0) qty
                FROM material_movements WHERE job_id=?""",
                (job_id,),
            )
            try:
                messages = self.ensure_in_progress_materials(job_id)
            except ValueError:
                continue
            if messages or (before and abs(float(before["qty"] or 0)) <= 0.0001):
                repaired += 1
        return repaired

    def auto_consume_job_materials(
        self,
        job_id: int,
        paint_coverage: float,
        mesh_coverage: float,
        *,
        movement_date: str | None = None,
    ) -> list[str]:
        """Check out the complete saved plan when work starts.

        This method deliberately reconciles *per material*.  A previous
        implementation only checked the total quantity across all materials,
        so one existing movement could incorrectly mark the whole job as
        deducted and leave the rest of the stock untouched.
        """
        with self.db.connection() as conn:
            job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if not job:
                raise ValueError("Trabajo no encontrado.")
            self._create_default_material_plan(conn, job_id, paint_coverage, mesh_coverage)
        return self.reconcile_job_materials_to_plan(
            job_id,
            movement_date=movement_date,
            note_prefix="Salida automática al iniciar el trabajo",
        )

    def _restore_job_materials_in_connection(
        self,
        conn: Any,
        job_id: int,
        *,
        return_date: str,
        note_prefix: str,
    ) -> list[str]:
        rows = conn.execute(
            """SELECT mm.material_id, materials.name, materials.unit,
            materials.category, materials.package_size, materials.average_unit_cost,
            COALESCE(SUM(CASE
                WHEN mm.movement_type='Consumo' THEN mm.quantity
                WHEN mm.movement_type='Devolución' THEN -mm.quantity
                ELSE 0 END),0) net_quantity
            FROM material_movements mm
            JOIN materials ON materials.id=mm.material_id
            WHERE mm.job_id=? AND mm.movement_type IN ('Consumo','Devolución')
            GROUP BY mm.material_id, materials.name, materials.unit, materials.category,
                     materials.package_size, materials.average_unit_cost
            HAVING net_quantity > 0.0001
            ORDER BY mm.material_id""",
            (job_id,),
        ).fetchall()
        if not rows:
            conn.execute("UPDATE jobs SET materials_deducted=0 WHERE id=?", (job_id,))
            return []

        descriptions: list[str] = []
        for row in rows:
            qty = float(row["net_quantity"] or 0)
            liters = (
                qty * float(row["package_size"] or 0)
                if str(row["category"]) == "Pintura"
                else 0.0
            )
            unit_cost = float(row["average_unit_cost"] or 0)
            conn.execute(
                """INSERT INTO material_movements(
                movement_date, material_id, movement_type, quantity, liters,
                unit_cost, total_cost, job_id, supplier, payment_status, amount_paid, notes
                ) VALUES (?, ?, 'Devolución', ?, ?, ?, ?, ?, '', 'No aplica', 0, ?)""",
                (
                    return_date, row["material_id"], qty, liters, unit_cost,
                    round(qty * unit_cost, 2), job_id, note_prefix,
                ),
            )
            self._recalculate_material_stock(conn, int(row["material_id"]))
            descriptions.append(
                f"Devuelto: {qty:g} {row['unit']}(s) de {row['name']}"
            )
        conn.execute("UPDATE jobs SET materials_deducted=0 WHERE id=?", (job_id,))
        return descriptions

    def restore_job_materials(
        self, job_id: int, *, return_date: str | None = None
    ) -> list[str]:
        """Return currently checked-out job materials to inventory.

        The original ``Consumo`` rows are preserved and matching
        ``Devolución`` rows are inserted. This keeps a complete audit trail
        while making the net inventory movement zero.
        """
        with self.db.connection() as conn:
            return self._restore_job_materials_in_connection(
                conn,
                job_id,
                return_date=return_date or date.today().isoformat(),
                note_prefix="Devolución al almacén por reprogramación del trabajo",
            )

    # ------------------------------------------------------------------
    # Deudas
    # ------------------------------------------------------------------
    def debt_summary(self) -> Mapping[str, float]:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(total_amount),0) total,
            COALESCE(SUM(amount_paid),0) paid,
            COALESCE(SUM(MAX(total_amount-amount_paid,0)),0) pending
            FROM debts"""
        )
        return {"total": float(row["total"]), "paid": float(row["paid"]), "pending": float(row["pending"])}

    def list_debts(self, filter_name: str = "Todas", term: str = "") -> list[Any]:
        clauses = ["(d.creditor LIKE ? OR d.notes LIKE ? OR COALESCE(m.name,'') LIKE ?)"]
        like = f"%{term.strip()}%"
        params: list[Any] = [like, like, like]
        if filter_name == "Pendientes":
            clauses.append("d.total_amount-d.amount_paid>0.005")
        elif filter_name == "Pagadas":
            clauses.append("d.total_amount-d.amount_paid<=0.005")
        elif filter_name == "Materiales":
            clauses.append("d.material_movement_id IS NOT NULL")
        elif filter_name == "Personales / otras":
            clauses.append("d.material_movement_id IS NULL")
        where = " AND ".join(clauses)
        return self.db.fetchall(
            f"""SELECT d.*, mm.supplier, m.name material,
            MAX(d.total_amount-d.amount_paid,0) balance_due,
            CASE WHEN d.total_amount-d.amount_paid<=0.005 THEN 'Pagada'
                 WHEN d.amount_paid>0 THEN 'Pago parcial' ELSE 'Pendiente' END payment_status
            FROM debts d
            LEFT JOIN material_movements mm ON mm.id=d.material_movement_id
            LEFT JOIN materials m ON m.id=mm.material_id
            WHERE {where}
            ORDER BY CASE WHEN d.total_amount-d.amount_paid>0.005 THEN 0 ELSE 1 END,
                     d.debt_date DESC, d.id DESC""",
            tuple(params),
        )

    def get_debt(self, debt_id: int) -> Any | None:
        return self.db.fetchone(
            """SELECT d.*, MAX(d.total_amount-d.amount_paid,0) balance_due,
            CASE WHEN d.total_amount-d.amount_paid<=0.005 THEN 'Pagada'
                 WHEN d.amount_paid>0 THEN 'Pago parcial' ELSE 'Pendiente' END payment_status
            FROM debts d WHERE d.id=?""",
            (debt_id,),
        )

    def save_debt(
        self,
        *,
        creditor: str,
        debt_date: str,
        total_amount: float,
        amount_paid: float,
        debt_type: str,
        notes: str,
        debt_id: int | None = None,
    ) -> int:
        creditor = creditor.strip()
        if not creditor:
            raise ValueError("Indica la persona o empresa a la que se debe.")
        total = max(float(total_amount), 0.0)
        paid = min(max(float(amount_paid), 0.0), total)
        with self.db.connection() as conn:
            if debt_id:
                old = conn.execute("SELECT * FROM debts WHERE id=?", (debt_id,)).fetchone()
                if not old:
                    raise ValueError("Deuda no encontrada.")
                conn.execute(
                    """UPDATE debts SET creditor=?, debt_date=?, total_amount=?, amount_paid=?,
                    debt_type=?, notes=? WHERE id=?""",
                    (creditor, debt_date, total, paid, debt_type, notes, debt_id),
                )
                delta = round(paid - float(old["amount_paid"]), 2)
                if abs(delta) > 0.005:
                    conn.execute(
                        """INSERT INTO debt_payments(debt_id, payment_date, amount, notes, source)
                        VALUES (?, ?, ?, ?, 'Ajuste')""",
                        (debt_id, debt_date, delta, "Ajuste manual del total pagado"),
                    )
                movement_id = old["material_movement_id"]
                if movement_id:
                    movement = conn.execute(
                        "SELECT * FROM material_movements WHERE id=?", (movement_id,)
                    ).fetchone()
                    status = self._payment_status(total, paid)
                    unit = round(total / float(movement["quantity"]), 4) if float(movement["quantity"]) > 0 else 0
                    conn.execute(
                        """UPDATE material_movements SET supplier=?, movement_date=?, total_cost=?,
                        unit_cost=?, amount_paid=?, payment_status=? WHERE id=?""",
                        (creditor, debt_date, total, unit, paid, status, movement_id),
                    )
                    if abs(delta) > 0.005:
                        conn.execute(
                            """INSERT INTO material_purchase_payments(movement_id, payment_date, amount, notes)
                            VALUES (?, ?, ?, ?)""",
                            (movement_id, debt_date, delta, "Ajuste realizado desde Deudas"),
                        )
                    self._recalculate_material_stock(conn, int(movement["material_id"]))
                return debt_id
            cur = conn.execute(
                """INSERT INTO debts(creditor, debt_date, total_amount, amount_paid, debt_type, notes)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (creditor, debt_date, total, paid, debt_type, notes),
            )
            saved_id = int(cur.lastrowid)
            if paid > 0.005:
                conn.execute(
                    """INSERT INTO debt_payments(debt_id, payment_date, amount, notes, source)
                    VALUES (?, ?, ?, ?, 'Inicial')""",
                    (saved_id, debt_date, paid, "Monto pagado al registrar la deuda"),
                )
            return saved_id

    def add_debt_payment(self, debt_id: int, payment_date: str, amount: float, notes: str = "") -> None:
        if amount <= 0:
            raise ValueError("El pago debe ser mayor que cero.")
        with self.db.connection() as conn:
            debt = conn.execute("SELECT * FROM debts WHERE id=?", (debt_id,)).fetchone()
            if not debt:
                raise ValueError("Deuda no encontrada.")
            balance = max(float(debt["total_amount"]) - float(debt["amount_paid"]), 0.0)
            if amount > balance + 0.005:
                raise ValueError(f"El pago supera el saldo pendiente de ${balance:,.2f}.")
            paid = round(float(debt["amount_paid"]) + amount, 2)
            conn.execute("UPDATE debts SET amount_paid=? WHERE id=?", (paid, debt_id))
            conn.execute(
                """INSERT INTO debt_payments(debt_id, payment_date, amount, notes, source)
                VALUES (?, ?, ?, ?, 'Deudas')""",
                (debt_id, payment_date, amount, notes),
            )
            if debt["material_movement_id"]:
                movement_id = int(debt["material_movement_id"])
                status = self._payment_status(float(debt["total_amount"]), paid)
                conn.execute(
                    "UPDATE material_movements SET amount_paid=?, payment_status=? WHERE id=?",
                    (paid, status, movement_id),
                )
                conn.execute(
                    """INSERT INTO material_purchase_payments(movement_id, payment_date, amount, notes)
                    VALUES (?, ?, ?, ?)""",
                    (movement_id, payment_date, amount, notes or "Pago registrado desde Deudas"),
                )

    def debt_payments(self, debt_id: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT * FROM debt_payments WHERE debt_id=?
            ORDER BY payment_date DESC, id DESC""",
            (debt_id,),
        )

    def get_debt_payment(self, payment_id: int) -> Any | None:
        return self.db.fetchone(
            """SELECT dp.*, d.creditor, d.debt_date, d.total_amount, d.amount_paid,
            d.material_movement_id
            FROM debt_payments dp JOIN debts d ON d.id=dp.debt_id
            WHERE dp.id=?""",
            (payment_id,),
        )

    def update_debt_payment(
        self, payment_id: int, payment_date: str, amount: float, notes: str = ""
    ) -> None:
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("El pago debe ser mayor que cero.")
        with self.db.connection() as conn:
            payment = conn.execute("SELECT * FROM debt_payments WHERE id=?", (payment_id,)).fetchone()
            if not payment:
                raise ValueError("El pago de la deuda ya no existe.")
            debt = conn.execute("SELECT * FROM debts WHERE id=?", (payment["debt_id"],)).fetchone()
            if not debt:
                raise ValueError("La deuda asociada al pago ya no existe.")
            if debt["material_movement_id"]:
                raise ValueError("Este pago está vinculado a materiales y debe corregirse como abono de materiales.")
            adjusted_paid = round(float(debt["amount_paid"] or 0) - float(payment["amount"] or 0) + amount, 2)
            if adjusted_paid < -0.005 or adjusted_paid - float(debt["total_amount"] or 0) > 0.005:
                available = float(debt["total_amount"] or 0) - (
                    float(debt["amount_paid"] or 0) - float(payment["amount"] or 0)
                )
                raise ValueError(f"El pago no puede superar ${max(available, 0):,.2f}.")
            conn.execute(
                "UPDATE debt_payments SET payment_date=?, amount=?, notes=? WHERE id=?",
                (payment_date, amount, notes.strip(), payment_id),
            )
            conn.execute("UPDATE debts SET amount_paid=? WHERE id=?", (max(adjusted_paid, 0.0), debt["id"]))

    def delete_debt_payment(self, payment_id: int) -> None:
        with self.db.connection() as conn:
            payment = conn.execute("SELECT * FROM debt_payments WHERE id=?", (payment_id,)).fetchone()
            if not payment:
                raise ValueError("El pago de la deuda ya no existe.")
            debt = conn.execute("SELECT * FROM debts WHERE id=?", (payment["debt_id"],)).fetchone()
            if not debt:
                raise ValueError("La deuda asociada al pago ya no existe.")
            if debt["material_movement_id"]:
                raise ValueError("Este pago está vinculado a materiales y debe eliminarse como abono de materiales.")
            adjusted_paid = max(round(float(debt["amount_paid"] or 0) - float(payment["amount"] or 0), 2), 0.0)
            conn.execute("DELETE FROM debt_payments WHERE id=?", (payment_id,))
            conn.execute("UPDATE debts SET amount_paid=? WHERE id=?", (adjusted_paid, debt["id"]))

    def clear_debt_legacy_payment(self, debt_id: int) -> None:
        """Remove the initial paid amount represented by the debt ledger row."""
        with self.db.connection() as conn:
            debt = conn.execute("SELECT * FROM debts WHERE id=?", (debt_id,)).fetchone()
            if not debt:
                raise ValueError("La deuda ya no existe.")
            if debt["material_movement_id"]:
                raise ValueError("La deuda está vinculada a materiales; edita la compra correspondiente.")
            detailed = conn.execute(
                "SELECT COALESCE(SUM(amount),0) total FROM debt_payments WHERE debt_id=?", (debt_id,)
            ).fetchone()
            paid = max(float(detailed["total"] or 0), 0.0)
            if abs(float(debt["amount_paid"] or 0) - paid) <= 0.005:
                raise ValueError("Esta deuda no tiene un pago inicial independiente que eliminar.")
            conn.execute("UPDATE debts SET amount_paid=? WHERE id=?", (paid, debt_id))

    # ------------------------------------------------------------------
    # Cobros y gastos
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Caja manual y préstamos por cobrar
    # ------------------------------------------------------------------
    def save_cash_movement(
        self,
        movement_date: str,
        direction: str,
        category: str,
        amount: float,
        notes: str = "",
        movement_id: int | None = None,
    ) -> int:
        direction = direction.strip().title()
        if direction not in {"Entrada", "Salida"}:
            raise ValueError("El movimiento debe ser una Entrada o una Salida.")
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("El monto debe ser mayor que cero.")
        category = category.strip() or "Otro"
        with self.db.connection() as conn:
            if movement_id:
                exists = conn.execute("SELECT id FROM cash_movements WHERE id=?", (movement_id,)).fetchone()
                if not exists:
                    raise ValueError("El movimiento de caja ya no existe.")
                conn.execute(
                    """UPDATE cash_movements SET movement_date=?, direction=?, category=?, amount=?, notes=?
                    WHERE id=?""",
                    (movement_date, direction, category, amount, notes.strip(), movement_id),
                )
                return int(movement_id)
            cur = conn.execute(
                """INSERT INTO cash_movements(movement_date, direction, category, amount, notes)
                VALUES (?, ?, ?, ?, ?)""",
                (movement_date, direction, category, amount, notes.strip()),
            )
            return int(cur.lastrowid)

    def get_cash_movement(self, movement_id: int) -> Any | None:
        return self.db.fetchone("SELECT * FROM cash_movements WHERE id=?", (movement_id,))

    def delete_cash_movement(self, movement_id: int) -> None:
        """Remove one manual cash movement.

        Movements shown in Caja are calculated from their source records.  This
        method is deliberately limited to the standalone ``cash_movements``
        table; linked records have their own delete methods below.
        """
        with self.db.connection() as conn:
            deleted = conn.execute("DELETE FROM cash_movements WHERE id=?", (movement_id,))
            if deleted.rowcount == 0:
                raise ValueError("El movimiento de caja ya no existe.")

    def list_manual_cash_movements(self, term: str = "", direction: str = "Todos") -> list[Any]:
        sql = "SELECT * FROM cash_movements WHERE 1=1"
        params: list[Any] = []
        if direction in {"Entrada", "Salida"}:
            sql += " AND direction=?"
            params.append(direction)
        term = term.strip()
        if term:
            sql += " AND (category LIKE ? OR notes LIKE ?)"
            like = f"%{term}%"
            params.extend([like, like])
        sql += " ORDER BY movement_date DESC, id DESC"
        return self.db.fetchall(sql, params)

    def cash_manual_summary(self) -> dict[str, float]:
        row = self.db.fetchone(
            """SELECT
            COALESCE(SUM(CASE WHEN direction='Entrada' THEN amount ELSE 0 END),0) incoming,
            COALESCE(SUM(CASE WHEN direction='Salida' THEN amount ELSE 0 END),0) outgoing
            FROM cash_movements"""
        )
        return {"incoming": float(row["incoming"] or 0), "outgoing": float(row["outgoing"] or 0)}

    def save_loan(
        self,
        borrower: str,
        loan_date: str,
        total_amount: float,
        notes: str = "",
        loan_id: int | None = None,
    ) -> int:
        borrower = borrower.strip()
        if not borrower:
            raise ValueError("Indica a quién le prestaste el dinero.")
        total = round(float(total_amount), 2)
        if total <= 0:
            raise ValueError("El monto prestado debe ser mayor que cero.")
        with self.db.connection() as conn:
            if loan_id:
                existing = conn.execute(
                    """SELECT lr.*, COALESCE((SELECT SUM(amount) FROM loan_repayments
                    WHERE loan_id=lr.id),0) repaid FROM loans_receivable lr WHERE lr.id=?""",
                    (loan_id,),
                ).fetchone()
                if not existing:
                    raise ValueError("El préstamo ya no existe.")
                if total + 0.005 < float(existing["repaid"] or 0):
                    raise ValueError("El monto total no puede ser menor que lo ya cobrado.")
                conn.execute(
                    """UPDATE loans_receivable SET borrower=?, loan_date=?, total_amount=?, notes=?
                    WHERE id=?""",
                    (borrower, loan_date, total, notes.strip(), loan_id),
                )
                return int(loan_id)
            cur = conn.execute(
                """INSERT INTO loans_receivable(borrower, loan_date, total_amount, notes)
                VALUES (?, ?, ?, ?)""",
                (borrower, loan_date, total, notes.strip()),
            )
            return int(cur.lastrowid)

    def get_loan(self, loan_id: int) -> Any | None:
        return self.db.fetchone(
            """SELECT lr.*, COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0) repaid,
            MAX(lr.total_amount-COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0),0) balance_due
            FROM loans_receivable lr WHERE lr.id=?""",
            (loan_id,),
        )

    def delete_loan(self, loan_id: int) -> None:
        with self.db.connection() as conn:
            deleted = conn.execute("DELETE FROM loans_receivable WHERE id=?", (loan_id,))
            if deleted.rowcount == 0:
                raise ValueError("El préstamo ya no existe.")

    def list_loans(self, term: str = "", filter_name: str = "Todos") -> list[Any]:
        sql = """SELECT lr.*,
        COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0) repaid,
        MAX(lr.total_amount-COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0),0) balance_due,
        CASE
          WHEN lr.total_amount-COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0)<=0.005 THEN 'Pagado'
          WHEN COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0)>0 THEN 'Pago parcial'
          ELSE 'Pendiente'
        END payment_status
        FROM loans_receivable lr WHERE 1=1"""
        params: list[Any] = []
        if filter_name == "Pendientes":
            sql += " AND lr.total_amount-COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0)>0.005"
        elif filter_name == "Pagados":
            sql += " AND lr.total_amount-COALESCE((SELECT SUM(amount) FROM loan_repayments WHERE loan_id=lr.id),0)<=0.005"
        term = term.strip()
        if term:
            sql += " AND (lr.borrower LIKE ? OR lr.notes LIKE ?)"
            like = f"%{term}%"
            params.extend([like, like])
        sql += " ORDER BY lr.loan_date DESC, lr.id DESC"
        return self.db.fetchall(sql, params)

    def loan_summary(self) -> dict[str, float]:
        row = self.db.fetchone(
            """SELECT COALESCE(SUM(total_amount),0) total,
            COALESCE((SELECT SUM(amount) FROM loan_repayments),0) repaid
            FROM loans_receivable"""
        )
        total = float(row["total"] or 0)
        repaid = float(row["repaid"] or 0)
        return {"total": total, "repaid": repaid, "pending": max(total - repaid, 0.0)}

    def add_loan_repayment(
        self, loan_id: int, payment_date: str, amount: float, notes: str = ""
    ) -> int:
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("El pago debe ser mayor que cero.")
        loan = self.get_loan(loan_id)
        if not loan:
            raise ValueError("El préstamo ya no existe.")
        balance = float(loan["balance_due"] or 0)
        if payment_date < str(loan["loan_date"]):
            raise ValueError("La fecha del cobro no puede ser anterior a la fecha del préstamo.")
        if amount - balance > 0.005:
            raise ValueError(f"El pago supera el saldo pendiente de ${balance:,.2f}.")
        return self.db.execute(
            """INSERT INTO loan_repayments(loan_id, payment_date, amount, notes)
            VALUES (?, ?, ?, ?)""",
            (loan_id, payment_date, amount, notes.strip()),
        )

    def get_loan_repayment(self, repayment_id: int) -> Any | None:
        return self.db.fetchone(
            """SELECT lp.*, lr.borrower, lr.loan_date, lr.total_amount
            FROM loan_repayments lp JOIN loans_receivable lr ON lr.id=lp.loan_id
            WHERE lp.id=?""",
            (repayment_id,),
        )

    def update_loan_repayment(
        self, repayment_id: int, payment_date: str, amount: float, notes: str = ""
    ) -> None:
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("El cobro debe ser mayor que cero.")
        with self.db.connection() as conn:
            payment = conn.execute(
                """SELECT lp.*, lr.loan_date, lr.total_amount FROM loan_repayments lp
                JOIN loans_receivable lr ON lr.id=lp.loan_id WHERE lp.id=?""",
                (repayment_id,),
            ).fetchone()
            if not payment:
                raise ValueError("El cobro del préstamo ya no existe.")
            if payment_date < str(payment["loan_date"]):
                raise ValueError("La fecha del cobro no puede ser anterior a la fecha del préstamo.")
            other = conn.execute(
                "SELECT COALESCE(SUM(amount),0) total FROM loan_repayments WHERE loan_id=? AND id<>?",
                (payment["loan_id"], repayment_id),
            ).fetchone()
            available = float(payment["total_amount"] or 0) - float(other["total"] or 0)
            if amount - available > 0.005:
                raise ValueError(f"El cobro supera el saldo disponible de ${max(available, 0):,.2f}.")
            conn.execute(
                "UPDATE loan_repayments SET payment_date=?, amount=?, notes=? WHERE id=?",
                (payment_date, amount, notes.strip(), repayment_id),
            )

    def delete_loan_repayment(self, repayment_id: int) -> None:
        with self.db.connection() as conn:
            deleted = conn.execute("DELETE FROM loan_repayments WHERE id=?", (repayment_id,))
            if deleted.rowcount == 0:
                raise ValueError("El cobro del préstamo ya no existe.")

    def loan_repayments(self, loan_id: int) -> list[Any]:
        return self.db.fetchall(
            """SELECT * FROM loan_repayments WHERE loan_id=?
            ORDER BY payment_date DESC, id DESC""",
            (loan_id,),
        )

    def cash_ledger(self, limit: int = 2000) -> list[dict[str, Any]]:
        """Libro de caja unificado, sin duplicar pagos vinculados a materiales."""
        rows: list[dict[str, Any]] = []

        def add(
            tx_date: str,
            direction: str,
            origin: str,
            concept: str,
            amount: float,
            notes: str = "",
            source_type: str = "",
            source_id: int | None = None,
            affects_cash: bool = True,
        ) -> None:
            if float(amount or 0) <= 0.005:
                return
            rows.append({
                "date": str(tx_date), "direction": direction, "origin": origin,
                "concept": concept, "amount": float(amount), "notes": notes or "",
                "source_type": source_type, "source_id": source_id,
                "affects_cash": bool(affects_cash),
            })

        for row in self.db.fetchall("SELECT * FROM cash_movements"):
            add(row["movement_date"], row["direction"], "Movimiento manual", row["category"], row["amount"], row["notes"], "manual", int(row["id"]))
        for row in self.db.fetchall(
            """SELECT p.*, c.name client, j.code FROM payments p
            JOIN jobs j ON j.id=p.job_id JOIN clients c ON c.id=j.client_id"""
        ):
            notes = row["notes"] or ""
            tip = float(row["tip_amount"] or 0)
            if tip > 0.005:
                notes = f"{notes} · Propina: ${tip:,.2f}" if notes else f"Propina: ${tip:,.2f}"
            add(
                row["payment_date"], "Entrada", "Trabajo",
                f"{row['payment_type']} · {row['client']}", row["amount"], notes,
                "job_payment", int(row["id"]),
                affects_cash=bool(int(row["affects_cash"] or 0)),
            )
        for row in self.db.fetchall("SELECT * FROM material_sales"):
            customer = (row["customer"] or "").strip() or "Cliente no especificado"
            add(row["sale_date"], "Entrada", "Venta de materiales", f"Venta · {customer}", row["total_amount"], row["notes"], "material_sale", int(row["id"]))
        for row in self.db.fetchall("SELECT * FROM expenses"):
            add(row["expense_date"], "Salida", "Gasto", row["description"], row["amount"], row["category"], "expense", int(row["id"]))
        for row in self.db.fetchall(
            """SELECT mpp.*, mm.supplier, m.name material FROM material_purchase_payments mpp
            JOIN material_movements mm ON mm.id=mpp.movement_id
            JOIN materials m ON m.id=mm.material_id"""
        ):
            add(row["payment_date"], "Salida", "Materiales", f"Pago · {row['supplier'] or row['material']}", row["amount"], row["notes"], "material_payment", int(row["id"]))
        for row in self.db.fetchall(
            """SELECT mm.*, m.name material,
            MAX(mm.amount_paid-COALESCE((SELECT SUM(amount) FROM material_purchase_payments WHERE movement_id=mm.id),0),0) legacy_paid
            FROM material_movements mm JOIN materials m ON m.id=mm.material_id
            WHERE mm.movement_type='Compra' AND mm.amount_paid>0.005"""
        ):
            add(row["movement_date"], "Salida", "Materiales", f"Pago inicial · {row['supplier'] or row['material']}", row["legacy_paid"], row["notes"], "material_purchase", int(row["id"]))
        for row in self.db.fetchall(
            """SELECT dp.*, d.creditor FROM debt_payments dp JOIN debts d ON d.id=dp.debt_id
            WHERE d.material_movement_id IS NULL"""
        ):
            add(row["payment_date"], "Salida", "Deuda", f"Pago · {row['creditor']}", row["amount"], row["notes"], "debt_payment", int(row["id"]))
        for row in self.db.fetchall(
            """SELECT d.*, MAX(d.amount_paid-COALESCE((SELECT SUM(amount) FROM debt_payments WHERE debt_id=d.id),0),0) legacy_paid
            FROM debts d WHERE d.material_movement_id IS NULL AND d.amount_paid>0.005"""
        ):
            add(row["debt_date"], "Salida", "Deuda", f"Pago inicial · {row['creditor']}", row["legacy_paid"], row["notes"], "debt", int(row["id"]))
        for row in self.db.fetchall(
            """SELECT j.id, j.completion_date, c.name client, COALESCE(SUM(jw.final_pay),0) total
            FROM jobs j JOIN clients c ON c.id=j.client_id JOIN job_workers jw ON jw.job_id=j.id
            WHERE j.status='Finalizado' AND j.completion_date IS NOT NULL
            GROUP BY j.id"""
        ):
            add(row["completion_date"], "Salida", "Nómina", f"Trabajo finalizado · {row['client']}", row["total"], "Salarios del trabajo", "payroll", int(row["id"]))
        for row in self.db.fetchall("SELECT * FROM loans_receivable"):
            add(row["loan_date"], "Salida", "Préstamo", f"Prestado a {row['borrower']}", row["total_amount"], row["notes"], "loan", int(row["id"]))
        for row in self.db.fetchall(
            """SELECT lp.*, lr.borrower FROM loan_repayments lp
            JOIN loans_receivable lr ON lr.id=lp.loan_id"""
        ):
            add(row["payment_date"], "Entrada", "Préstamo", f"Cobro de {row['borrower']}", row["amount"], row["notes"], "loan_payment", int(row["id"]))

        rows.sort(key=lambda item: (item["date"], int(item.get("source_id") or 0)), reverse=True)
        return rows[:limit]

    def job_payment_summary(
        self, job_id: int, agreed_price: float | None = None
    ) -> dict[str, float]:
        job = self.db.fetchone("SELECT agreed_price FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise ValueError("Trabajo no encontrado.")
        paid_row = self.db.fetchone(
            """SELECT COALESCE(SUM(MAX(amount - COALESCE(tip_amount, 0), 0)),0) paid
            FROM payments WHERE job_id=?""",
            (job_id,),
        )
        paid = float(paid_row["paid"] or 0)
        total = float(job["agreed_price"] if agreed_price is None else agreed_price or 0)
        return {"total": total, "paid": paid, "balance": max(total - paid, 0.0)}

    def add_payment(
        self, job_id: int, payment_date: str, payment_type: str,
        amount: float, notes: str, affects_cash: bool | None = None,
        tip_amount: float = 0.0,
    ) -> int:
        amount = round(float(amount), 2)
        tip_amount = round(float(tip_amount), 2)
        if amount < 0:
            raise ValueError("El monto del cobro no puede ser negativo.")
        if tip_amount < 0:
            raise ValueError("La propina no puede ser negativa.")
        if affects_cash is None:
            affects_cash = "extranjero" not in payment_type.casefold()
        total_amount = round(amount + tip_amount, 2)
        return self.db.execute(
            """INSERT INTO payments(payment_date, job_id, payment_type, amount, affects_cash, tip_amount, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (payment_date, job_id, payment_type, total_amount, int(affects_cash), tip_amount, notes),
        )

    def payments(self, job_id: int | None = None) -> list[Any]:
        if job_id is not None:
            return self.db.fetchall(
                "SELECT * FROM payments WHERE job_id=? ORDER BY payment_date DESC, id DESC",
                (job_id,),
            )
        return self.db.fetchall(
            """SELECT payments.*, jobs.code, clients.name client FROM payments
            JOIN jobs ON jobs.id=payments.job_id
            JOIN clients ON clients.id=jobs.client_id
            ORDER BY payment_date DESC, payments.id DESC"""
        )

    def payment(self, payment_id: int, job_id: int | None = None) -> Any | None:
        sql = "SELECT * FROM payments WHERE id=?"
        params: list[Any] = [payment_id]
        if job_id is not None:
            sql += " AND job_id=?"
            params.append(job_id)
        return self.db.fetchone(sql, params)

    def update_payment(
        self,
        payment_id: int,
        job_id: int,
        payment_date: str,
        payment_type: str,
        amount: float,
        notes: str,
        tip_amount: float = 0.0,
    ) -> None:
        amount = round(float(amount), 2)
        tip_amount = round(float(tip_amount), 2)
        if amount <= 0:
            raise ValueError("El monto del cobro debe ser mayor que cero.")
        if tip_amount < 0:
            raise ValueError("La propina no puede ser negativa.")
        with self.db.connection() as conn:
            existing = conn.execute(
                "SELECT id FROM payments WHERE id=? AND job_id=?",
                (payment_id, job_id),
            ).fetchone()
            if not existing:
                raise ValueError("El cobro ya no existe en este trabajo.")
            conn.execute(
                """UPDATE payments SET payment_date=?, payment_type=?, amount=?,
                affects_cash=?, tip_amount=?, notes=? WHERE id=? AND job_id=?""",
                (
                    payment_date,
                    payment_type,
                    round(amount + tip_amount, 2),
                    int("extranjero" not in payment_type.casefold()),
                    tip_amount,
                    notes.strip(),
                    payment_id,
                    job_id,
                ),
            )

    def delete_payment(self, payment_id: int, job_id: int) -> None:
        with self.db.connection() as conn:
            cur = conn.execute(
                "DELETE FROM payments WHERE id=? AND job_id=?",
                (payment_id, job_id),
            )
            if cur.rowcount == 0:
                raise ValueError("El cobro ya no existe en este trabajo.")

    def save_expense(
        self,
        expense_date: str,
        description: str,
        amount: float,
        category: str,
        job_id: int | None,
        expense_id: int | None = None,
    ) -> int:
        description = description.strip()
        if not description:
            raise ValueError("Indica la descripción del gasto.")
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("El monto del gasto debe ser mayor que cero.")
        category = category.strip() or "General"
        with self.db.connection() as conn:
            if expense_id:
                exists = conn.execute("SELECT id FROM expenses WHERE id=?", (expense_id,)).fetchone()
                if not exists:
                    raise ValueError("El gasto ya no existe.")
                conn.execute(
                    """UPDATE expenses SET expense_date=?, description=?, amount=?, category=?, job_id=?
                    WHERE id=?""",
                    (expense_date, description, amount, category, job_id, expense_id),
                )
                return int(expense_id)
            cur = conn.execute(
                """INSERT INTO expenses(expense_date, description, amount, category, job_id)
                VALUES (?, ?, ?, ?, ?)""",
                (expense_date, description, amount, category, job_id),
            )
            return int(cur.lastrowid)

    def add_expense(
        self, expense_date: str, description: str, amount: float,
        category: str, job_id: int | None,
    ) -> int:
        """Compatibility wrapper for existing callers that register a new expense."""
        return self.save_expense(expense_date, description, amount, category, job_id)

    def get_expense(self, expense_id: int) -> Any | None:
        return self.db.fetchone("SELECT * FROM expenses WHERE id=?", (expense_id,))

    def delete_expense(self, expense_id: int) -> None:
        with self.db.connection() as conn:
            deleted = conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
            if deleted.rowcount == 0:
                raise ValueError("El gasto ya no existe.")

    def expenses(self) -> list[Any]:
        return self.db.fetchall(
            """SELECT expenses.*, jobs.code FROM expenses
            LEFT JOIN jobs ON jobs.id=expenses.job_id
            ORDER BY expense_date DESC, expenses.id DESC"""
        )

    # ------------------------------------------------------------------
    # Reportes
    # ------------------------------------------------------------------
    def crew_report(self) -> list[Any]:
        return self.db.fetchall(
            """SELECT crews.name, COUNT(DISTINCT jobs.id) jobs_count,
            COALESCE(SUM(jobs.new_area),0) new_area,
            COALESCE(SUM(jobs.maintenance_area),0) maintenance_area,
            COALESCE(SUM(jobs.agreed_price),0) amount,
            COALESCE((SELECT SUM(jw.final_pay) FROM job_workers jw
              JOIN jobs j2 ON j2.id=jw.job_id
              WHERE j2.crew_id=crews.id AND j2.status='Finalizado'),0) payroll
            FROM crews LEFT JOIN jobs
              ON jobs.crew_id=crews.id AND jobs.status='Finalizado'
            GROUP BY crews.id ORDER BY crews.id"""
        )

    def worker_report(self) -> list[Any]:
        return self.db.fetchall(
            """SELECT workers.name,
            COUNT(DISTINCT CASE WHEN jobs.status='Finalizado' THEN jobs.id END) jobs_count,
            COALESCE(SUM(CASE WHEN jobs.status='Finalizado'
              AND jw.counts_for_worker_meters=1 THEN jobs.new_area ELSE 0 END),0) meters,
            COALESCE(SUM(CASE WHEN jobs.status='Finalizado'
              THEN jw.final_pay ELSE 0 END),0) pay
            FROM workers LEFT JOIN job_workers jw ON jw.worker_id=workers.id
            LEFT JOIN jobs ON jobs.id=jw.job_id
            GROUP BY workers.id ORDER BY workers.name"""
        )
