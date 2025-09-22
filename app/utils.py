from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Iterable, List, Sequence

from .schemas import ServiceOrderCreate

EXPECTED_HEADERS = {
    "nome": "customer_name",
    "endereco": "address",
    "id_instalacao": "installation_id",
    "plano": "plan",
    "data_agendamento": "scheduled_date",
}


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def parse_orders_csv(data: bytes) -> List[ServiceOrderCreate]:
    """Parse a CSV file containing service orders.

    Expected headers (case insensitive): nome, endereco, id_instalacao, plano, data_agendamento
    """

    buffer = io.StringIO(data.decode("utf-8-sig"))
    reader = csv.DictReader(buffer)
    if not reader.fieldnames:
        raise ValueError("Arquivo CSV sem cabeçalho")

    columns = {normalize_header(name): name for name in reader.fieldnames}

    missing_columns = [label for label in EXPECTED_HEADERS if label not in columns]
    if missing_columns:
        raise ValueError(
            "Colunas obrigatórias ausentes no arquivo: " + ", ".join(missing_columns)
        )

    orders: List[ServiceOrderCreate] = []
    for row in reader:
        if not any(value.strip() for value in row.values() if value):
            continue
        kwargs = {}
        for header, field_name in EXPECTED_HEADERS.items():
            raw_value = row[columns[header]].strip()
            if header == "data_agendamento":
                try:
                    value = datetime.strptime(raw_value, "%Y-%m-%d").date()
                except ValueError as exc:
                    raise ValueError(
                        f"Data inválida '{raw_value}' para a ordem {row}"
                    ) from exc
            else:
                value = raw_value
            kwargs[field_name] = value
        orders.append(ServiceOrderCreate(**kwargs))
    return orders
