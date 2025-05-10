'''
Author: Aditya Bhatt 10:17 AM 09-05-2025

NOTE:    

BUG(Not a bug but a note):
1.df=await read_file_from_blob_to_df(file_url)
This operation is little tricky because "df" is a pandas dataframe and we need to load it in the memory to process it.(All this can not be done in the api server)
So this is will all this needs to be done in a worker node.Before working on filters we need to fix this
(Fixed)

'''
import pandas as pd


async def get_filters(df:pd.DataFrame):
    columns_datatypes=df.dtypes.to_dict()
    output_dict={}
    for column,datatype in columns_datatypes.items():
        output_dict[column]={"type":str(datatype)}
    #For iteration 1 we will remove all columns from the output_dict which have int or float datatype
    for column,datatype in columns_datatypes.items():
        if datatype in ["int64","float64","int32","float32"]:
            output_dict.pop(column)

        
    return output_dict










