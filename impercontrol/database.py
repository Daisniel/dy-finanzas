from __future__ import annotations

import sqlite3
import shutil
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator


APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "impercontrol.db"


class Database:
    def __init__(self, path: Path | str = DB_PATH) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA synchronous = NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS crews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            base_crew_id INTEGER,
            base_role TEXT NOT NULL DEFAULT 'Ayudante',
            is_partner INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(base_crew_id) REFERENCES crews(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_id INTEGER NOT NULL,
            measured_date TEXT NOT NULL,
            raw_text TEXT DEFAULT '',
            new_area REAL NOT NULL DEFAULT 0,
            maintenance_area REAL NOT NULL DEFAULT 0,
            total_area REAL NOT NULL DEFAULT 0,
            price_new REAL NOT NULL DEFAULT 10,
            price_maintenance REAL NOT NULL DEFAULT 6,
            masonry_extra REAL NOT NULL DEFAULT 0,
            membrane_extra REAL NOT NULL DEFAULT 0,
            manual_adjustment REAL NOT NULL DEFAULT 0,
            final_price REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'Medido',
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS measurement_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measurement_id INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            expression TEXT NOT NULL,
            result REAL NOT NULL DEFAULT 0,
            work_type TEXT NOT NULL DEFAULT 'Desde cero',
            section TEXT NOT NULL DEFAULT 'Techo',
            observation TEXT DEFAULT '',
            FOREIGN KEY(measurement_id) REFERENCES measurements(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            measurement_id INTEGER,
            client_id INTEGER NOT NULL,
            crew_id INTEGER,
            status TEXT NOT NULL DEFAULT 'Medido',
            measurement_date TEXT,
            scheduled_date TEXT,
            start_date TEXT,
            completion_date TEXT,
            maintenance_due_date TEXT,
            new_area REAL NOT NULL DEFAULT 0,
            maintenance_area REAL NOT NULL DEFAULT 0,
            agreed_price REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            maintenance_contacted INTEGER NOT NULL DEFAULT 0,
            maintenance_contact_date TEXT,
            maintenance_contact_result TEXT DEFAULT '',
            materials_deducted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(measurement_id) REFERENCES measurements(id) ON DELETE SET NULL,
            FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE CASCADE,
            FOREIGN KEY(crew_id) REFERENCES crews(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS job_workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            worker_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            rate_new REAL NOT NULL DEFAULT 0,
            rate_maintenance REAL NOT NULL DEFAULT 0.3,
            base_pay REAL NOT NULL DEFAULT 0,
            rounded_pay REAL NOT NULL DEFAULT 0,
            manual_adjustment REAL NOT NULL DEFAULT 0,
            adjustment_reason TEXT DEFAULT '',
            final_pay REAL NOT NULL DEFAULT 0,
            paid INTEGER NOT NULL DEFAULT 0,
            counts_for_worker_meters INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(worker_id) REFERENCES workers(id) ON DELETE CASCADE,
            UNIQUE(job_id, worker_id)
        );

        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            unit TEXT NOT NULL,
            package_size REAL NOT NULL DEFAULT 0,
            stock_quantity REAL NOT NULL DEFAULT 0,
            stock_liters REAL NOT NULL DEFAULT 0,
            average_unit_cost REAL NOT NULL DEFAULT 0,
            minimum_stock REAL NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS material_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_date TEXT NOT NULL,
            customer TEXT DEFAULT '',
            total_amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS material_sale_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            unit_price REAL NOT NULL DEFAULT 0,
            cost_unit REAL NOT NULL DEFAULT 0,
            total_price REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sale_id) REFERENCES material_sales(id) ON DELETE CASCADE,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS material_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_date TEXT NOT NULL,
            material_id INTEGER NOT NULL,
            movement_type TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            liters REAL NOT NULL DEFAULT 0,
            unit_cost REAL NOT NULL DEFAULT 0,
            total_cost REAL NOT NULL DEFAULT 0,
            job_id INTEGER,
            sale_id INTEGER,
            supplier TEXT DEFAULT '',
            brand TEXT DEFAULT '',
            payment_status TEXT NOT NULL DEFAULT 'Pagado',
            amount_paid REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL,
            FOREIGN KEY(sale_id) REFERENCES material_sales(id) ON DELETE CASCADE
        );



        CREATE TABLE IF NOT EXISTS material_purchase_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(movement_id) REFERENCES material_movements(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creditor TEXT NOT NULL,
            debt_date TEXT NOT NULL,
            total_amount REAL NOT NULL DEFAULT 0,
            amount_paid REAL NOT NULL DEFAULT 0,
            debt_type TEXT NOT NULL DEFAULT 'Otra',
            material_movement_id INTEGER UNIQUE,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(material_movement_id) REFERENCES material_movements(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS debt_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            debt_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL,
            notes TEXT DEFAULT '',
            source TEXT NOT NULL DEFAULT 'Manual',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(debt_id) REFERENCES debts(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS job_material_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            quantity REAL NOT NULL DEFAULT 0,
            liters REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE,
            FOREIGN KEY(material_id) REFERENCES materials(id) ON DELETE CASCADE,
            UNIQUE(job_id, material_id)
        );

        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_date TEXT NOT NULL,
            job_id INTEGER NOT NULL,
            payment_type TEXT NOT NULL DEFAULT 'Cobro',
            amount REAL NOT NULL,
            affects_cash INTEGER NOT NULL DEFAULT 1,
            tip_amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            expense_date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL DEFAULT 'General',
            job_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(job_id) REFERENCES jobs(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS cash_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movement_date TEXT NOT NULL,
            direction TEXT NOT NULL CHECK(direction IN ('Entrada','Salida')),
            category TEXT NOT NULL DEFAULT 'Otro',
            amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS loans_receivable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            borrower TEXT NOT NULL,
            loan_date TEXT NOT NULL,
            total_amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS loan_repayments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER NOT NULL,
            payment_date TEXT NOT NULL,
            amount REAL NOT NULL DEFAULT 0,
            notes TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(loan_id) REFERENCES loans_receivable(id) ON DELETE CASCADE
        );
        """
        with self.connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(schema)
            # Lightweight migration for databases created by earlier versions.
            columns = {row[1] for row in conn.execute("PRAGMA table_info(measurement_lines)")}
            if "section" not in columns:
                conn.execute("ALTER TABLE measurement_lines ADD COLUMN section TEXT NOT NULL DEFAULT 'Techo'")

            job_columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
            if "measurement_date" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN measurement_date TEXT")
            if "materials_deducted" not in job_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN materials_deducted INTEGER NOT NULL DEFAULT 0")

            # Normaliza los estados de versiones anteriores al flujo actual.
            # Las columnas antiguas se conservan para compatibilidad, pero la UI
            # y la lógica ya utilizan measurement_date en lugar de scheduled_date.
            conn.execute(
                """UPDATE jobs
                SET measurement_date = COALESCE(
                    NULLIF(measurement_date, ''),
                    (SELECT measured_date FROM measurements WHERE measurements.id=jobs.measurement_id),
                    NULLIF(scheduled_date, ''),
                    substr(created_at, 1, 10),
                    date('now')
                )
                WHERE measurement_date IS NULL OR TRIM(measurement_date)=''"""
            )
            conn.execute(
                """UPDATE jobs SET status = CASE
                    WHEN status IN ('Confirmado', 'Finalizado') THEN status
                    WHEN status IN ('Aprobado', 'Programado') THEN 'Confirmado'
                    WHEN status IN ('En progreso', 'En Progreso') THEN 'En Progreso'
                    WHEN status='Completado' THEN 'Finalizado'
                    WHEN status IN ('Medido', 'Presupuestado', 'Pendiente', 'Cancelado') THEN 'Medido'
                    ELSE 'Medido'
                END"""
            )
            conn.execute(
                """UPDATE measurements SET status = CASE
                    WHEN status IN ('Confirmado', 'Finalizado') THEN status
                    WHEN status IN ('Aprobado', 'Programado') THEN 'Confirmado'
                    WHEN status IN ('En progreso', 'En Progreso') THEN 'En Progreso'
                    WHEN status='Completado' THEN 'Finalizado'
                    WHEN status IN ('Medido', 'Presupuestado', 'Pendiente', 'Cancelado') THEN 'Medido'
                    ELSE 'Medido'
                END"""
            )

            movement_columns = {row[1] for row in conn.execute("PRAGMA table_info(material_movements)")}
            if "supplier" not in movement_columns:
                conn.execute("ALTER TABLE material_movements ADD COLUMN supplier TEXT DEFAULT ''")
            if "brand" not in movement_columns:
                conn.execute("ALTER TABLE material_movements ADD COLUMN brand TEXT DEFAULT ''")
            if "payment_status" not in movement_columns:
                conn.execute("ALTER TABLE material_movements ADD COLUMN payment_status TEXT NOT NULL DEFAULT 'Pagado'")
            if "amount_paid" not in movement_columns:
                conn.execute("ALTER TABLE material_movements ADD COLUMN amount_paid REAL NOT NULL DEFAULT 0")
                conn.execute("UPDATE material_movements SET amount_paid=total_cost WHERE movement_type='Compra'")
            if "sale_id" not in movement_columns:
                conn.execute("ALTER TABLE material_movements ADD COLUMN sale_id INTEGER")

            payment_columns = {row[1] for row in conn.execute("PRAGMA table_info(payments)")}
            if "affects_cash" not in payment_columns:
                conn.execute("ALTER TABLE payments ADD COLUMN affects_cash INTEGER NOT NULL DEFAULT 1")
            if "tip_amount" not in payment_columns:
                conn.execute("ALTER TABLE payments ADD COLUMN tip_amount REAL NOT NULL DEFAULT 0")

            # v0.6.9: payments made abroad are visible in Caja for audit, but
            # they do not increase local cash.  v0.6.8 temporarily normalized
            # every payment as cash; restore the business rule for historical
            # rows based on their payment type.
            conn.execute(
                """UPDATE payments SET affects_cash = CASE
                    WHEN LOWER(payment_type) LIKE '%extranjero%' THEN 0
                    ELSE 1
                END"""
            )

            # v0.6.6: ``liters`` is a derived value for paint.  Older builds let
            # the quantity change without recalculating this field, which could
            # leave records such as 28 cubetas de 19 L = 19 L.  Besides showing
            # a wrong value, the old stock validator used that stale liters
            # total and could incorrectly block a job with "inventario
            # negativo" even when there were enough buckets.  Normalize all
            # historical rows and rebuild the material summary from the movement
            # ledger every time the database opens.  The operation is idempotent.
            conn.execute(
                """UPDATE material_movements
                SET liters = CASE
                    WHEN EXISTS(
                        SELECT 1 FROM materials m
                        WHERE m.id=material_movements.material_id AND m.category='Pintura'
                    ) THEN quantity * COALESCE((
                        SELECT m.package_size FROM materials m
                        WHERE m.id=material_movements.material_id
                    ), 0)
                    ELSE 0
                END"""
            )
            conn.execute(
                """UPDATE job_material_plans
                SET liters = CASE
                    WHEN EXISTS(
                        SELECT 1 FROM materials m
                        WHERE m.id=job_material_plans.material_id AND m.category='Pintura'
                    ) THEN quantity * COALESCE((
                        SELECT m.package_size FROM materials m
                        WHERE m.id=job_material_plans.material_id
                    ), 0)
                    ELSE 0
                END"""
            )
            for material in conn.execute(
                "SELECT id, category, package_size FROM materials"
            ).fetchall():
                aggregate = conn.execute(
                    """SELECT COUNT(*) movement_count,
                    COALESCE(SUM(CASE
                        WHEN movement_type IN ('Compra','Devolución') THEN quantity
                        WHEN movement_type IN ('Consumo','Venta') THEN -quantity
                        ELSE 0 END),0) qty,
                    COALESCE(SUM(CASE WHEN movement_type='Compra' THEN total_cost ELSE 0 END),0) purchase_value,
                    COALESCE(SUM(CASE WHEN movement_type='Compra' THEN quantity ELSE 0 END),0) purchased_qty
                    FROM material_movements WHERE material_id=?""",
                    (material["id"],),
                ).fetchone()
                if int(aggregate["movement_count"] or 0) <= 0:
                    continue
                qty = float(aggregate["qty"] or 0)
                # Do not invent stock if a legacy ledger is truly negative; the
                # repository will surface a precise error on the next edit.
                safe_qty = max(qty, 0.0)
                liters = (
                    safe_qty * float(material["package_size"] or 0)
                    if str(material["category"]) == "Pintura"
                    else 0.0
                )
                purchased_qty = float(aggregate["purchased_qty"] or 0)
                average = (
                    float(aggregate["purchase_value"] or 0) / purchased_qty
                    if purchased_qty > 0
                    else 0.0
                )
                conn.execute(
                    "UPDATE materials SET stock_quantity=?, stock_liters=?, average_unit_cost=? WHERE id=?",
                    (safe_qty, liters, average, material["id"]),
                )

            # Existing unpaid material purchases become linked supplier debts.
            conn.execute(
                """INSERT OR IGNORE INTO debts(
                creditor, debt_date, total_amount, amount_paid, debt_type,
                material_movement_id, notes
                )
                SELECT CASE WHEN TRIM(supplier)<>'' THEN supplier ELSE 'Proveedor sin especificar' END,
                       movement_date, total_cost, amount_paid, 'Materiales', id,
                       'Deuda importada automáticamente desde una compra de materiales'
                FROM material_movements
                WHERE movement_type='Compra' AND total_cost-amount_paid>0.005"""
            )
        self.seed_defaults()

    def seed_defaults(self) -> None:
        defaults = {
            "price_new": "10",
            "price_maintenance": "6",
            "maintenance_years": "3",
            "maintenance_warning_days": "90",
            "paint_coverage_m2": "25",
            "mesh_roll_coverage_m2": "100",
            "rate_crew1_leader_new": "0.7",
            "rate_crew2_leader_new": "0.6",
            "rate_helper_new": "0.5",
            "rate_partner_new": "0.7",
            "rate_admin_crew2_new": "0.3",
            "rate_maintenance": "0.3",
            "font_size_increment": "0",
            "theme_name": "Claro",
            "cash_opening_balance": "0",
        }
        with self.connection() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
                defaults.items(),
            )
            conn.execute("INSERT OR IGNORE INTO crews(name) VALUES ('Brigada 1')")
            conn.execute("INSERT OR IGNORE INTO crews(name) VALUES ('Brigada 2')")
            crews = {r["name"]: r["id"] for r in conn.execute("SELECT id, name FROM crews")}
            workers = [
                ("Jefe Brigada 1", crews.get("Brigada 1"), "Jefe / Administrador", 0),
                ("Ayudante Brigada 1", crews.get("Brigada 1"), "Ayudante", 0),
                ("Jefe Brigada 2", crews.get("Brigada 2"), "Jefe", 0),
                ("Ayudante Brigada 2", crews.get("Brigada 2"), "Ayudante", 0),
                ("Socio", None, "Socio", 1),
            ]
            conn.executemany(
                """
                INSERT OR IGNORE INTO workers(name, base_crew_id, base_role, is_partner)
                VALUES (?, ?, ?, ?)
                """,
                workers,
            )
            materials = [
                ("Malla de refuerzo 100 m", "Malla", "rollo", 100, 0, 0, 0, 1),
                ("Pintura impermeabilizante 19 L", "Pintura", "cubeta", 19, 0, 0, 0, 2),
                ("Pintura impermeabilizante 16 L", "Pintura", "cubeta", 16, 0, 0, 0, 2),
            ]
            conn.executemany(
                """
                INSERT OR IGNORE INTO materials(
                    name, category, unit, package_size, stock_quantity,
                    stock_liters, average_unit_cost, minimum_stock
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                materials,
            )

    def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        with self.connection() as conn:
            cur = conn.execute(sql, tuple(params))
            return int(cur.lastrowid)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        with self.connection() as conn:
            conn.executemany(sql, rows)

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self.connection() as conn:
            return conn.execute(sql, tuple(params)).fetchone()

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(sql, tuple(params)).fetchall()

    def get_setting(self, key: str, default: str = "") -> str:
        row = self.fetchone("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: Any) -> None:
        self.execute(
            """
            INSERT INTO settings(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )

    def backup(self, destination: Path | str) -> Path:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as source, sqlite3.connect(destination) as target:
            source.backup(target)
        return destination


    def restore(self, source: Path | str) -> Path:
        """Replace the active database after validating the selected SQLite file."""
        source = Path(source)
        if not source.exists() or not source.is_file():
            raise ValueError("El archivo de base de datos seleccionado no existe.")
        try:
            with sqlite3.connect(source) as conn:
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                required = {"settings", "clients", "measurements", "jobs"}
                if not required.issubset(tables):
                    raise ValueError("El archivo no parece ser una base de datos válida de D&Y Finanzas.")
                check = conn.execute("PRAGMA integrity_check").fetchone()
                if not check or check[0] != "ok":
                    raise ValueError("La base de datos seleccionada no superó la verificación de integridad.")
        except sqlite3.DatabaseError as exc:
            raise ValueError("El archivo seleccionado no es una base de datos SQLite válida.") from exc

        temp = self.path.with_suffix(".importando.db")
        shutil.copy2(source, temp)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(self.path) + suffix)
            if sidecar.exists():
                sidecar.unlink()
        temp.replace(self.path)
        self.initialize()
        return self.path

    def next_job_code(self) -> str:
        prefix = datetime.now().strftime("TR-%Y-")
        row = self.fetchone(
            "SELECT code FROM jobs WHERE code LIKE ? ORDER BY id DESC LIMIT 1",
            (f"{prefix}%",),
        )
        if not row:
            return f"{prefix}0001"
        try:
            number = int(row["code"].split("-")[-1]) + 1
        except (ValueError, IndexError):
            number = 1
        return f"{prefix}{number:04d}"

    @staticmethod
    def today_iso() -> str:
        return date.today().isoformat()
