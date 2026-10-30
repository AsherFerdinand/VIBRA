"""Bounded validated CSV import with explicit SI units; never resamples data."""

import csv
import io

from vibra.signals.models import MAX_SAMPLES, Provenance, SignalError, SignalSeries, SignalUnit

MAX_CSV_BYTES = 10 * 1024 * 1024


def import_signal_csv(
    data: bytes,
    unit: SignalUnit,
    time_column: str = "time",
    signal_column: str = "signal",
    filename: str = "signal.csv",
) -> SignalSeries:
    if len(data) > MAX_CSV_BYTES:
        raise SignalError("CSV exceeds the 10 MiB input limit.")
    if not time_column or not signal_column or time_column == signal_column:
        raise SignalError("Select distinct, nonempty time and signal column names.")
    try:
        reader = csv.reader(io.StringIO(data.decode("utf-8-sig")), strict=True)
        header = [name.strip() for name in next(reader)]
        if (
            not 2 <= len(header) <= 64
            or len(set(header)) != len(header)
            or any(not h for h in header)
        ):
            raise SignalError("CSV requires 2–64 unique, nonempty column headers.")
        if time_column not in header or signal_column not in header:
            raise SignalError("Selected columns are absent from the CSV header.")
        time_index, value_index = header.index(time_column), header.index(signal_column)
        times: list[float] = []
        values: list[float] = []
        for line, row in enumerate(reader, start=2):
            if len(times) >= MAX_SAMPLES:
                raise SignalError(f"CSV exceeds {MAX_SAMPLES} samples.")
            if (
                len(row) != len(header)
                or not row[time_index].strip()
                or not row[value_index].strip()
            ):
                raise SignalError(f"Missing/ragged data on CSV line {line}.")
            times.append(float(row[time_index]))
            values.append(float(row[value_index]))
    except (UnicodeError, csv.Error, StopIteration, ValueError) as exc:
        if isinstance(exc, SignalError):
            raise
        raise SignalError(f"Invalid UTF-8/numeric CSV: {exc}") from exc
    return SignalSeries(
        time=tuple(times),
        values=tuple(values),
        unit=unit,
        provenance=Provenance(
            kind="csv",
            label=filename,
            details={
                "time_column": time_column,
                "signal_column": signal_column,
                "time_unit": "s",
                "signal_unit": unit,
                "resampling": "none",
            },
        ),
    )
