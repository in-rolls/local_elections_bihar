"""Common schema declarations and column metadata."""

import pandera.polars as pa


def field(description, **checks):
    return pa.Field(description=description, **checks)


def nullable(description, **checks):
    return pa.Field(description=description, nullable=True, **checks)


def polars_schema(model):
    return {
        name: column.dtype.type for name, column in model.to_schema().columns.items()
    }


def dictionary_rows(name, model):
    schema = model.to_schema()
    for column, spec in schema.columns.items():
        yield {
            "table": f"{name}.parquet",
            "column": column,
            "type": str(spec.dtype),
            "nullable": spec.nullable,
            "checks": "; ".join(str(c) for c in spec.checks),
            "description": spec.description,
        }
