# NOTE- This document is written by AI Agent please verify the content before using it.
# How to generate dashboards.

## High-Level Design Document: Auto Dashboard System

### 1. Introduction

This document describes the high-level architecture and design of the Auto Dashboard feature for the Deep Analysis platform. The goal is to enable fully interactive, embeddable dashboards in a React-based frontend, driven by a FastAPI backend that supplies structured JSON specifications and filtered data.

### 2. Architecture Overview

```
+------------------+          +-----------------+          +--------------------+
|  React Frontend  | <------> |  FastAPI Backend| <------> |  Data Processing   |
| (Dashboard App)  |   JSON   | (API Endpoints) |   Pandas   | (CSV → KPIs/Charts)|
+------------------+          +-----------------+          +--------------------+
```

* **Frontend**: React application using charting libraries (Recharts, Plotly.js, or similar).
* **Backend**: FastAPI application exposing REST endpoints returning JSON specs.
* **Data Processing**: Pandas-based modules that load CSVs, compute KPIs, generate chart data.

### 3. Key Components

#### 3.1 Agents

* **Auto Dashboard Agent**: Orchestrates the dashboard generation pipeline by:

  * Triggering CSV ingestion via the `POST /api/upload` endpoint
  * Fetching filter metadata (`GET /api/filters`)
  * Requesting KPI calculations (`GET /api/kpis`)
  * Requesting chart specifications (`GET /api/charts`)
  * Gathering business insights (`GET /api/insights`)
  * Optionally, consolidating calls via `GET /api/dashboard` for a unified payload

#### 3.2 FastAPI Backend

* **Endpoints**:

  * `POST /api/upload`

    * Accepts a CSV file upload and returns a task ID or dataset ID for subsequent calls.
  * `GET /api/filters`

    * Returns available filter metadata (dimensions and their possible values) for the uploaded dataset.
  * `GET /api/kpis`

    * Query Params: filter criteria (e.g., `?category=Sales&date_range=Last30Days`)
    * Response: List of KPI objects (name, current\_value, prev\_value, status).
  * `GET /api/charts`

    * Query Params: same filters as KPIs.
    * Response: List of chart specs (chart\_type, title, values, optional options).
  * `GET /api/insights`

    * Query Params: same filters as above.
    * Response: Business insights text or structured insights objects based on filtered data.
  * `GET /api/dashboard` *(optional)*

    * Query Params: all filters.
    * Response: Combined payload with `kpis`, `charts`, `filters`, and `insights` in one request for convenience.

#### 3.3 React Frontend

* **Components**:

  * `<FilterPanel>`: Renders dynamic filter controls (dropdowns, date pickers).
  * `<KpiCard>`: Displays individual KPI metrics.
  * `<ChartRenderer>`: Switches on `chart_type` and renders appropriate chart component.
  * `<Dashboard>`: Orchestrates data fetching, state management, and layout.

* **Interaction Flow**:

  1. On load, the Auto Dashboard Agent invokes `GET /api/filters`, `/api/kpis`, and `/api/charts` with default filters for initial state.
  2. User updates filter UI.
  3. Frontend triggers new fetch to `/api/kpis`, `/api/charts`, and `/api/insights` with updated query params (or the Auto Dashboard Agent uses `GET /api/dashboard`).
  4. State updates and re-renders KPI cards and charts.

### 4. JSON Schema Definitions

#### 4.1 Filters Response

```json
{
  "filters": {
    "category": ["Finance", "Sales", "HR"],
    "region": ["North", "South", "East", "West"],
    "date_range": ["Last7Days", "Last30Days", "YearToDate"]
  }
}
```

#### 4.2 KPIs Response

```json
{
  "kpis": [
    {
      "kpi_name": "Total Sales",
      "current_value": 15000,
      "prev_value": 12000,
      "good_bad": "good"
    },
    ...
  ]
}
```

#### 4.3 Charts Response

```json
{
  "charts": [
    {
      "chart_title": "Sales by Region",
      "chart_type": "pie",
      "values": {
        "North": 5000,
        "South": 4000,
        "East": 3000,
        "West": 3000
      },
      "options": { "showLegend": true }
    },
    {
      "chart_title": "Monthly Revenue",
      "chart_type": "line",
      "values": { "Jan": 2000, "Feb": 3000, "Mar": 4000 },
      "options": { "xAxisLabel": "Month", "yAxisLabel": "Revenue" }
    }
  ]
}
```

### 5. Deployment Considerations

* **Backend**: Containerize FastAPI (Docker) and deploy on Azure Web App or Kubernetes.
* **Frontend**: Host React app on Vercel, Netlify, or Azure Static Web Apps.
* **CORS**: Configure CORS in FastAPI to allow frontend domain.
* **Scaling**: Scale backend separately from frontend; use Azure Functions or serverless for spikes.

### 6. Extensibility & Future Enhancements

* **Advanced Specs**: Evolve chart specs to Vega‑Lite or Plotly JSON for richer visuals.
* **Authentication**: Add token‑based auth to API.
* **Real‑time Data**: Integrate WebSockets for live updates.
* **Custom Themes**: Pass CSS theme tokens in JSON to brand the dashboard dynamically.

---

*End of Document*
