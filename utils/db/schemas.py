from pydantic import BaseModel

class title_schema(BaseModel):
    title:str

class date_finder_schema(BaseModel):
    date_column:str

class filter_schema(BaseModel):
    filters:list[str]
