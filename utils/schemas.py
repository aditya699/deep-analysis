from pydantic import BaseModel


class KPI(BaseModel):
    kpi_names:list[str]
