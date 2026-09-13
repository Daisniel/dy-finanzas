from __future__ import annotations

import ast
import math
import operator
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable


_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


class SafeMathError(ValueError):
    pass


def safe_evaluate(expression: str) -> float:
    """Evaluate only numbers, parentheses and basic arithmetic operations."""
    try:
        node = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise SafeMathError(str(exc)) from exc

    def visit(current: ast.AST) -> float:
        if isinstance(current, ast.Expression):
            return visit(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, (int, float)):
            return float(current.value)
        if isinstance(current, ast.BinOp) and type(current.op) in _ALLOWED_BINOPS:
            left = visit(current.left)
            right = visit(current.right)
            result = _ALLOWED_BINOPS[type(current.op)](left, right)
            if abs(result) > 1e12:
                raise SafeMathError("Resultado fuera de rango")
            return float(result)
        if isinstance(current, ast.UnaryOp) and type(current.op) in _ALLOWED_UNARY:
            return float(_ALLOWED_UNARY[type(current.op)](visit(current.operand)))
        raise SafeMathError("La expresión contiene elementos no permitidos")

    result = visit(node)
    if not math.isfinite(result):
        raise SafeMathError("El resultado no es finito")
    return result


def round_to_nearest_five(value: float) -> float:
    value_dec = Decimal(str(value)) / Decimal("5")
    rounded = value_dec.quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("5")
    return float(rounded)


@dataclass(slots=True)
class ParsedLine:
    original_text: str
    expression: str
    result: float
    work_type: str
    observation: str
    section: str = "Techo"
    valid: bool = True
    error: str = ""


KEYWORD_TYPES = {
    "mantenimiento": "Mantenimiento",
    "mant.": "Mantenimiento",
    "mant ": "Mantenimiento",
    "desde cero": "Desde cero",
    "nuevo": "Desde cero",
    "nueva": "Desde cero",
}


def _normalize_expression(text: str) -> str:
    normalized = text.replace(",", ".")
    normalized = normalized.replace("×", "*").replace("X", "*").replace("x", "*")
    normalized = normalized.replace("÷", "/")
    # Permit the common '^' notation but translate it to Python exponentiation.
    normalized = normalized.replace("^", "**")
    # Keep only arithmetic characters. Text remains available as observation.
    normalized = re.sub(r"[^0-9.+\-*/() ]", " ", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"(?<!\*)\*(?!\*){2,}", "*", normalized)
    normalized = re.sub(r"^[*/]+|[+\-*/]+$", "", normalized)
    while "()" in normalized:
        normalized = normalized.replace("()", "")
    return normalized


def _extract_observation(original: str, expression: str) -> str:
    observation = original
    # Remove obvious dimensions and operators, preserving human notes.
    observation = re.sub(r"\d+(?:[.,]\d+)?", " ", observation)
    observation = observation.replace("×", " ").replace("x", " ").replace("X", " ")
    observation = re.sub(r"[()+\-*/=^]", " ", observation)
    observation = re.sub(r"\s+", " ", observation).strip(" .,-")
    return observation


def parse_measurement_text(raw_text: str) -> list[ParsedLine]:
    """Parse measurement lines while preserving Techo/Pretiles sections.

    Headings such as ``Techo`` and ``Pretiles`` change the section for the
    following measurements. Existing results written after ``=`` are ignored
    and recalculated, which makes it possible to paste old WhatsApp quotes.
    """
    parsed: list[ParsedLine] = []
    current_section = "Techo"
    skip_next_summary_value = False

    for raw_line in raw_text.splitlines():
        original = raw_line.strip()
        if not original:
            continue
        if skip_next_summary_value:
            skip_next_summary_value = False
            continue

        simple = re.sub(r"[^a-záéíóúñ ]", "", original.lower()).strip()
        if simple in {"techo", "techos", "area de techo", "área de techo"}:
            current_section = "Techo"
            continue
        if simple in {"pretil", "pretiles", "area de pretiles", "área de pretiles"}:
            current_section = "Pretiles"
            continue
        if simple.startswith("total") or simple.startswith("costo total"):
            skip_next_summary_value = True
            continue

        lower = f" {original.lower()} "
        work_type = "Desde cero"
        for keyword, detected_type in KEYWORD_TYPES.items():
            if keyword in lower:
                work_type = detected_type
                break

        # Many old quotes already contain '= 51,65'. Recalculate from the
        # expression before '=' instead of accidentally treating the result as
        # another operand.
        expression_source = original.split("=", 1)[0]
        expression = _normalize_expression(expression_source)
        observation = _extract_observation(expression_source, expression)
        if not expression or not re.search(r"\d", expression):
            parsed.append(
                ParsedLine(original, expression, 0, work_type, observation, current_section, False, "No se encontró una operación")
            )
            continue
        try:
            result = round(safe_evaluate(expression), 2)
            parsed.append(ParsedLine(original, expression, result, work_type, observation, current_section))
        except (SafeMathError, ZeroDivisionError, OverflowError) as exc:
            parsed.append(ParsedLine(original, expression, 0, work_type, observation, current_section, False, str(exc)))
    return parsed


def calculate_budget(
    new_area: float,
    maintenance_area: float,
    price_new: float,
    price_maintenance: float,
    masonry_extra: float = 0,
    membrane_extra: float = 0,
    manual_adjustment: float = 0,
) -> float:
    return round(
        new_area * price_new
        + maintenance_area * price_maintenance
        + masonry_extra
        + membrane_extra
        + manual_adjustment,
        2,
    )


def estimate_materials(
    total_area: float,
    paint_coverage: float = 25,
    roll_coverage: float = 100,
    mesh_area: float | None = None,
) -> dict[str, float]:
    """Estimate paint for all treated area and mesh only for new-work area."""
    paint_source = max(total_area, 0)
    mesh_source = paint_source if mesh_area is None else max(mesh_area, 0)
    paint = math.ceil(paint_source / max(paint_coverage, 1)) if paint_source > 0 else 0
    mesh = math.ceil(mesh_source / max(roll_coverage, 1)) if mesh_source > 0 else 0
    return {"paint_buckets": float(paint), "mesh_rolls": float(mesh)}


def add_years_iso(date_text: str, years: int) -> str:
    source = date.fromisoformat(date_text)
    try:
        target = source.replace(year=source.year + years)
    except ValueError:  # 29 February
        target = source.replace(month=2, day=28, year=source.year + years)
    return target.isoformat()


def salary_base(new_area: float, maintenance_area: float, rate_new: float, rate_maintenance: float) -> float:
    return round(new_area * rate_new + maintenance_area * rate_maintenance, 2)


def totals_by_type(lines: Iterable[ParsedLine]) -> tuple[float, float, float]:
    new_area = sum(line.result for line in lines if line.valid and line.work_type == "Desde cero")
    maintenance_area = sum(line.result for line in lines if line.valid and line.work_type == "Mantenimiento")
    return round(new_area, 2), round(maintenance_area, 2), round(new_area + maintenance_area, 2)
