# 🦆 DuckDB Guide for Fast Analytical Dashboards

## 📌 Overview

DuckDB is an embedded, in-process SQL OLAP database optimized for analytics. It can run fast SQL queries on large CSV, Parquet, and even Pandas DataFrames directly — without needing to load everything in memory. It's perfect for use cases like dashboard engines, ad hoc analytics, and LLM-powered insights.

---

## ✅ Why Use DuckDB

| Feature                    | Benefit                                          |
| -------------------------- | ------------------------------------------------ |
| **No server**              | Works like SQLite — no deployment needed         |
| **Columnar engine**        | Super fast filtering, grouping, and aggregations |
| **Reads CSV/Parquet**      | Directly without full memory load                |
| **SQL support**            | Familiar SQL for complex analysis                |
| **Vectorized**             | Processes rows in batches (C++ speed)            |
| **Integrates with Pandas** | Query DataFrames directly                        |

---

## 🚀 Installation

```bash
pip install duckdb
```

---

## 📂 Basic Usage

### Run SQL on CSV

```python
import duckdb

result = duckdb.query("""
    SELECT category, SUM(sales) AS total_sales
    FROM 'sales.csv'
    WHERE region = 'North'
    GROUP BY category
""").df()
```

### Query a Pandas DataFrame

```python
import pandas as pd
import duckdb

df = pd.read_csv("sales.csv")
result = duckdb.query("SELECT category, AVG(sales) FROM df GROUP BY category").df()
```

---

## 📊 Use Case: KPI API with Filters

### Function

```python
def get_kpi(csv_path, filters: dict):
    where_clause = " AND ".join([f"{k}='{v}'" for k, v in filters.items()])
    query = f"""
        SELECT category, SUM(sales) AS total_sales
        FROM '{csv_path}'
        WHERE {where_clause}
        GROUP BY category
    """
    return duckdb.query(query).df()
```

---

## ⚙️ Integration in Dashboard Engine

1. Upload CSV → store in blob storage
2. Download to `/tmp/xyz.csv` for query
3. Pass file path + filters to DuckDB
4. Run query → return to frontend as JSON

---

## ⚡ Tips

* Store CSVs locally before querying
* Use parameterized SQL to avoid injection
* Avoid row-by-row logic (use Pandas if needed)
* Use `LIMIT` and `ORDER BY` for preview queries

---

## 📌 Summary

DuckDB is the fastest and easiest way to build an analytical engine into your backend. Use it for querying large CSVs, returning filtered KPIs, and generating chart-ready results — all with minimal setup.

It's a perfect companion for FastAPI + React dashboards or LLM-powered insights systems.

---

## 📚 Resources

* [https://duckdb.org](https://duckdb.org)
* [DuckDB Python API Docs](https://duckdb.org/docs/api/python)

