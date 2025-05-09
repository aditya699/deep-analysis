# Filters Feature — Notes

This feature defines how filters are selected, processed, and served in the AI Dashboard backend.

---

## 🏗️ Overview

- Use an LLM to identify the **top 3–4 most relevant columns** for filters.
- Include only **categorical** and **date** columns.
- Skip **numerical** columns.

---

## 📦 API Endpoints

### POST `/get_filters`

- Returns top 20 unique values for each selected filter.
- Marks high-cardinality columns for “Load more” on the frontend.

Example response:
```json
{
  "filters": {
    "country": ["India", "USA", "Germany"],
    "product": ["A", "B", "C"],
    "order_date": ["2023-Jan", "2023-Feb"]
  },
  "high_cardinality_columns": ["product"]
}
````

---

### POST `/get_more_values`

* Returns additional values for a high-cardinality column.

Example input:

```json
{
  "file_id": "abc123",
  "column": "product",
  "offset": 20,
  "limit": 50
}
```

---

## 📅 Date Handling

* Date columns are transformed into **month-year format**:

  * Example: `2023-01-12` → `2023-Jan`

---

## ⚙️ Cardinality Handling

* Send only **top 20 values** in `/get_filters`.
* Use `/get_more_values` to fetch more values on demand.

---

## 🔥 Summary

* ✅ Categorical + date columns only
* ✅ Top 20 values returned
* ✅ “Load more” handled via separate endpoint
* ✅ Dates shown as month-year
