from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Sequence

from .formatters import round_area
from .logic import (
    ParsedLine,
    add_years_iso,
    calculate_budget,
    estimate_materials,
    parse_measurement_text,
    round_to_nearest_five,
    salary_base,
)
from .repositories import AppRepository


@dataclass(slots=True)
class MeasurementTotals:
    new_area: float = 0.0
    maintenance_area: float = 0.0
    total_area: float = 0.0


@dataclass(slots=True)
class PayrollLine:
    worker_id: int
    name: str
    role: str
    rate_new: float
    rate_maintenance: float
    base_pay: float = 0.0
    rounded_pay: float = 0.0
    manual_adjustment: float = 0.0
    adjustment_reason: str = ""
    final_pay: float = 0.0
    counts_for_worker_meters: bool = True


class MeasurementService:
    def __init__(self, repository: AppRepository) -> None:
        self.repo = repository

    def parse(self, raw_text: str) -> list[ParsedLine]:
        return parse_measurement_text(raw_text)

    def calculate_expression_result(self, expression: str) -> float:
        """Calculate one editable measurement expression.

        The same parser used for pasted WhatsApp measurements is reused here so
        expressions edited from a work keep exactly the same arithmetic rules
        as a new measurement.
        """
        parsed = self.parse(expression.strip())
        if len(parsed) != 1 or not parsed[0].valid:
            raise ValueError("La expresión no es una medida válida.")
        return float(parsed[0].result)

    def totals_from_rows(self, rows: Iterable[Mapping[str, Any]]) -> MeasurementTotals:
        new_area = 0.0
        maintenance = 0.0
        for row in rows:
            try:
                result = float(row.get("result", 0))
            except (TypeError, ValueError):
                result = 0.0
            work_type = str(row.get("work_type", "Desde cero")).lower()
            if "manten" in work_type:
                maintenance += result
            else:
                new_area += result
        return MeasurementTotals(
            new_area=round(new_area, 2),
            maintenance_area=round(maintenance, 2),
            total_area=round(new_area + maintenance, 2),
        )

    def calculate_price(
        self,
        totals: MeasurementTotals,
        price_new: float,
        price_maintenance: float,
        masonry_extra: float,
        membrane_extra: float,
        manual_adjustment: float,
    ) -> float:
        return calculate_budget(
            totals.new_area,
            totals.maintenance_area,
            price_new,
            price_maintenance,
            masonry_extra,
            membrane_extra,
            manual_adjustment,
        )

    def estimate_materials(self, totals: MeasurementTotals) -> dict[str, float]:
        return estimate_materials(
            totals.total_area,
            self.repo.setting_float("paint_coverage_m2", 25.0),
            self.repo.setting_float("mesh_roll_coverage_m2", 100.0),
            mesh_area=totals.new_area,
        )

    def save(
        self,
        *,
        client_id: int,
        measured_date: str,
        raw_text: str,
        rows: Sequence[Mapping[str, Any]],
        totals: MeasurementTotals,
        price_new: float,
        price_maintenance: float,
        masonry_extra: float,
        membrane_extra: float,
        manual_adjustment: float,
        final_price: float,
        status: str,
        notes: str,
        measurement_id: int | None = None,
    ) -> int:
        payload = {
            "client_id": client_id,
            "measured_date": measured_date,
            "raw_text": raw_text,
            "new_area": totals.new_area,
            "maintenance_area": totals.maintenance_area,
            "total_area": totals.total_area,
            "price_new": price_new,
            "price_maintenance": price_maintenance,
            "masonry_extra": masonry_extra,
            "membrane_extra": membrane_extra,
            "manual_adjustment": manual_adjustment,
            "final_price": final_price,
            "status": status,
            "notes": notes,
        }
        return self.repo.save_measurement(payload, rows, measurement_id)

    @staticmethod
    def format_decimal_es(value: float, decimals: int = 2) -> str:
        return f"{value:.{decimals}f}".replace(".", ",")

    def build_whatsapp_quote(
        self,
        rows: Sequence[Mapping[str, Any]],
        total_area: float,
        final_price: float,
    ) -> str:
        sections: dict[str, list[Mapping[str, Any]]] = {"Techo": [], "Pretiles": []}
        for row in rows:
            section = str(row.get("section", "Techo")).strip().title()
            if section not in sections:
                section = "Techo"
            sections[section].append(row)

        output: list[str] = []
        for section in ("Techo", "Pretiles"):
            values = sections[section]
            if not values:
                continue
            output.append(section)
            section_total = 0.0
            for row in values:
                expression = str(row.get("expression", "")).replace("**", "^").replace("*", " x ")
                result = float(row.get("result", 0))
                observation = str(row.get("observation", "")).strip()
                section_total += result
                suffix = f" ({observation})" if observation else ""
                output.append(
                    f"{expression}{suffix} = {self.format_decimal_es(result)}"
                )
            output.append(
                f"{'Total de Pretiles' if section == 'Pretiles' else 'Total del Techo'} "
                f"{self.format_decimal_es(section_total)} m²"
            )
            output.append("")

        output.extend(
            [
                f"Total del Área {self.format_decimal_es(round_area(total_area), 0)} m²",
                "",
                f"Costo Total del trabajo {self.format_decimal_es(final_price)} USD",
            ]
        )
        return "\n".join(output).strip()


class PayrollService:
    def __init__(self, repository: AppRepository) -> None:
        self.repo = repository

    def default_lines(self, crew_name: str) -> list[PayrollLine]:
        workers = {row["name"]: row for row in self.repo.workers_basic(True)}
        maintenance_rate = self.repo.setting_float("rate_maintenance", 0.3)
        if crew_name == "Brigada 2":
            defaults = [
                ("Jefe Brigada 2", "Jefe", self.repo.setting_float("rate_crew2_leader_new", 0.6), True),
                ("Ayudante Brigada 2", "Ayudante", self.repo.setting_float("rate_helper_new", 0.5), True),
                ("Socio", "Socio", self.repo.setting_float("rate_partner_new", 0.7), False),
                ("Jefe Brigada 1", "Administrador", self.repo.setting_float("rate_admin_crew2_new", 0.3), False),
            ]
        else:
            defaults = [
                ("Jefe Brigada 1", "Jefe / Administrador", self.repo.setting_float("rate_crew1_leader_new", 0.7), True),
                ("Ayudante Brigada 1", "Ayudante", self.repo.setting_float("rate_helper_new", 0.5), True),
                ("Socio", "Socio", self.repo.setting_float("rate_partner_new", 0.7), False),
            ]
        result: list[PayrollLine] = []
        for name, role, rate, counts in defaults:
            worker = workers.get(name)
            if worker:
                result.append(
                    PayrollLine(
                        worker_id=int(worker["id"]),
                        name=name,
                        role=role,
                        rate_new=rate,
                        rate_maintenance=maintenance_rate,
                        counts_for_worker_meters=counts,
                    )
                )
        return result

    @staticmethod
    def calculate_line(line: PayrollLine, new_area: float, maintenance_area: float) -> PayrollLine:
        line.base_pay = salary_base(
            new_area, maintenance_area, line.rate_new, line.rate_maintenance
        )
        line.rounded_pay = round_to_nearest_five(line.base_pay)
        line.final_pay = round(line.rounded_pay + line.manual_adjustment, 2)
        return line

    def calculate_all(
        self, lines: Sequence[PayrollLine], new_area: float, maintenance_area: float
    ) -> list[PayrollLine]:
        return [self.calculate_line(line, new_area, maintenance_area) for line in lines]

    def save(self, job_id: int, lines: Sequence[PayrollLine]) -> None:
        self.repo.replace_job_payroll(job_id, [asdict(line) for line in lines])


class JobService:
    VALID_STATUSES = ("Medido", "Confirmado", "En Progreso", "Finalizado")

    def __init__(self, repository: AppRepository) -> None:
        self.repo = repository

    def save_job(
        self,
        *,
        job_id: int,
        current_job: Mapping[str, Any],
        status: str,
        crew_id: int | None,
        measurement_date: str,
        start_date: str | None,
        agreed_price: float,
        notes: str,
        new_area: float | None = None,
        maintenance_area: float | None = None,
        phone: str | None = None,
        address: str | None = None,
        auto_deduct_materials: bool = False,
        completion_date: str | None = None,
        measurement_rows: Sequence[Mapping[str, Any]] | None = None,
    ) -> list[str]:
        if status not in self.VALID_STATUSES:
            raise ValueError("Estado de trabajo no válido.")
        if not measurement_date:
            raise ValueError("La fecha de medición es obligatoria.")

        current_status = str(current_job["status"])
        today_iso = date.today().isoformat()
        effective_status = status
        stored_start: str | None = None
        if status in {"Confirmado", "En Progreso", "Finalizado"}:
            if not start_date:
                raise ValueError("Indica la fecha de inicio del trabajo.")
            stored_start = start_date
            if current_status == "En Progreso" and status == "Confirmado" and start_date <= today_iso:
                raise ValueError(
                    "Para reprogramar un trabajo en progreso, selecciona una nueva fecha de inicio posterior a hoy."
                )
            if status == "Confirmado" and start_date <= today_iso:
                effective_status = "En Progreso"

        stored_completion = current_job["completion_date"]
        stored_due = current_job["maintenance_due_date"]
        material_messages: list[str] = []

        entering_progress = (
            effective_status == "En Progreso"
            and current_status not in {"En Progreso", "Finalizado"}
        )
        leaving_progress = (
            current_status == "En Progreso"
            and effective_status in {"Medido", "Confirmado"}
        )

        if leaving_progress:
            material_messages.extend(
                self.repo.restore_job_materials(job_id, return_date=today_iso)
            )
        elif entering_progress:
            material_messages.extend(
                self.repo.auto_consume_job_materials(
                    job_id,
                    self.repo.setting_float("paint_coverage_m2", 25.0),
                    self.repo.setting_float("mesh_roll_coverage_m2", 100.0),
                    movement_date=stored_start or today_iso,
                )
            )

        if effective_status == "Finalizado":
            # La fecha se registra en el momento en que el usuario confirma la
            # finalización. Solo se conserva una anterior si el trabajo ya estaba
            # finalizado y se vuelve a editar.
            if current_status != "Finalizado" or not stored_completion:
                stored_completion = completion_date or today_iso
            years = self.repo.setting_int("maintenance_years", 3)
            stored_due = add_years_iso(str(stored_completion), years)
            if auto_deduct_materials and not int(current_job["materials_deducted"]):
                material_messages.extend(
                    self.repo.auto_consume_job_materials(
                        job_id,
                        self.repo.setting_float("paint_coverage_m2", 25.0),
                        self.repo.setting_float("mesh_roll_coverage_m2", 100.0),
                        movement_date=stored_start or stored_completion,
                    )
                )
        elif current_status != "Finalizado":
            stored_completion = None
            stored_due = None

        job_values: dict[str, Any] = {
            "status": effective_status,
            "crew_id": crew_id,
            "measurement_date": measurement_date,
            "start_date": stored_start,
            "completion_date": stored_completion,
            "maintenance_due_date": stored_due,
            "new_area": float(current_job["new_area"]) if new_area is None else float(new_area),
            "maintenance_area": float(current_job["maintenance_area"]) if maintenance_area is None else float(maintenance_area),
            "phone": current_job["client_phone"] if phone is None else phone,
            "address": current_job["client_address"] if address is None else address,
            "agreed_price": agreed_price,
            "notes": notes,
        }
        if measurement_rows is not None:
            # Persist the detailed breakdown in the same work update. The
            # caller already recalculates the totals before reaching this
            # point; keeping the rows here prevents a job and its measurement
            # from drifting apart when the work is edited from Trabajos.
            job_values["measurement_rows"] = measurement_rows
        self.repo.update_job(job_id, job_values)
        return material_messages



class ApplicationServices:
    def __init__(self, repository: AppRepository) -> None:
        self.repo = repository
        self.measurements = MeasurementService(repository)
        self.payroll = PayrollService(repository)
        self.jobs = JobService(repository)
