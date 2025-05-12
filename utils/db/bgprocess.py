'''
This file will be used to implement functions that will be doing the heavy lifting of the background tasks

'''
import pandas as pd
import numpy as np
import io
import requests
from fastapi import HTTPException
from utils.db.process import get_client_mongo
from azure.storage.blob import BlobServiceClient, ContainerClient
from datetime import datetime
from utils.db.process import get_blob_client, get_container_client
from utils.db.schemas import title_schema,date_finder_schema,filter_schema
from agents import Agent,Runner
from utils.prompts import TITLE_PROMPT,DATE_FINDER_PROMPT,DATE_COLUMN_PROCESSOR_PROMPT,DEBUG_PROMPT_DASHBOARD,FILTER_PROMPT
from utils.db.filters import get_filters
from contextlib import redirect_stdout
from io import StringIO

async def read_file_from_blob_to_df(blob_url: str) -> pd.DataFrame:
    '''
    Reads a file from blob storage and converts it to a pandas DataFrame.
    This function is designed to run in the background and process files asynchronously.
    
    Args:
        blob_url (str): The URL of the blob storage file
        
    Returns:
        pd.DataFrame: The data loaded into a pandas DataFrame
        
    Raises:
        HTTPException: If there's an error reading the file
    '''
    try:
        # Download the file content using requests instead of trying to access blob directly
        # This is more reliable when working with URLs
        response = requests.get(blob_url)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Convert to DataFrame
        df = pd.read_csv(io.BytesIO(response.content))
        
        # Update the process in mongo db
        mongo_client = await get_client_mongo()
        db = mongo_client["Python-Data-Analyst"]
        collection = db["file_uploads-db"]
        await collection.update_one(
            {"file_url": blob_url},
            {"$set": {
                "status": "Data Loaded in DataFrame",
                "updated_at": datetime.now().isoformat()
            }}
        )
        return df
    except Exception as e:
        # Update MongoDB with error status
        mongo_client = await get_client_mongo()
        db = mongo_client["Python-Data-Analyst"]
        collection = db["file_uploads-db"]
        await collection.update_one(
            {"file_url": blob_url},
            {"$set": {
                "status": "error",
                "error_message": str(e),
                "updated_at": datetime.now().isoformat()
            }}
        )
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

async def process_file_background(blob_url: str) -> str:

    '''
    Background task to process files from blob storage.
    This function will be called by the background worker.
    
    Args:
        blob_url (str): The URL of the blob storage file
        
    Returns:
        str: A message indicating the processing result
        
    Raises:
        HTTPException: If there's an error processing the file
    '''
    try:
        # Update MongoDB with processing status
        mongo_client = await get_client_mongo()
        db = mongo_client["Python-Data-Analyst"]
        collection = db["file_uploads-db"]
        
        try:
            df = await read_file_from_blob_to_df(blob_url)
            columns = df.columns.tolist()
            #filter out all columns with int or float datatype
            all_filters=[column for column in columns if df[column].dtype not in ["int64","float64","int32","float32"]]
            print("All Filters: ",all_filters)
            # Update MongoDB with success status and all filters and columns
            await collection.update_one(
                {"file_url": blob_url},
                {"$set": {
                    "status": "Data Loaded in DataFrame",
                    "columns": columns,
                    "all_filters": all_filters,
                    "updated_at": datetime.now().isoformat()
                }}
            )

            # Get the dashboard title
            title=await get_dashboard_title(df)

            #Update MongoDB with title
            await collection.update_one(
                {"file_url": blob_url},
                {"$set": {"title": title,"updated_at": datetime.now().isoformat(),"status":"Dashboard Title Generated"}}
            )
            print("Dashboard Title Generated")

            #Get the filters
            filters,date_column,df=await get_dashboard_filters(df)
            print("Filters Generated and Date Column Generated")
            print(filters)
            print(date_column)
            if date_column != "No":
                # Check if month_year is a column in the dataframe
                if 'month_year' in df.columns:
                    print(df["month_year"].unique())
                else:
                    print("month_year column not found in dataframe")

            #Update MongoDB with filters
            await collection.update_one(
                {"file_url": blob_url},
                {"$set": {"filters": filters,"updated_at": datetime.now().isoformat(),"status":"Filters Generated"}}
            )

            #Update MongoDB with date column
            await collection.update_one(
                {"file_url": blob_url},
                {"$set": {"date_column": date_column,"updated_at": datetime.now().isoformat(),"status":"Date Column Generated"}}
            )

            print("Date Column Generated")
            print("Filters Generated")
            
            #Are we able to print values in the filter
            for i in filters:
                print(len(df[i].unique()))


            return f"Processing completed. Columns: {columns}, Filters: {filters}, Date Column: {date_column}"
        except Exception as e:
            # Update MongoDB with error status
            await collection.update_one(
                {"file_url": blob_url},
                {"$set": {
                    "status": "error",
                    "error_message": str(e),
                    "updated_at": datetime.now().isoformat()
                }}
            )
            raise e
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
async def get_dashboard_title(df:pd.DataFrame)->str:
    '''
    This function will be used to generate a title for the dashboard.

    Args:
        df (pd.DataFrame): The dataframe to get the title of
        mongo_client (AsyncIOMotorClient): The MongoDB client
    Returns:
        str: The title of the dashboard
        
    
    '''
    try:
        columns=df.columns.tolist()
        prompt=TITLE_PROMPT+"Here are the columns of the dataframe: "+str(columns)
        agent_title=Agent(name="Title",instructions=TITLE_PROMPT,model="gpt-4.1-nano-2025-04-14",output_type=title_schema)
        title_result=await Runner.run(agent_title,prompt)
        title=title_result.final_output.title
        return title
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def execute_with_debug(code, namespace, error_context, df:pd.DataFrame, date_column, max_attempts=3):
    '''
    Execute code with debugging capabilities, retrying up to max_attempts times.
    
    Args:
        code (str): The code to execute
        namespace (dict): The namespace to execute the code in
        error_context (str): The error context to provide to the LLM
        df (pd.DataFrame): The dataframe to execute the code on
        date_column (str): The date column in the dataframe
        max_attempts (int): The maximum number of attempts to execute the code
        
    Returns:
        pd.DataFrame: The processed dataframe
    '''
    
    error_history = []  # Store error history for context
    current_code = code
    
    for attempt in range(1, max_attempts + 1):
        try:
            # Execute the code in the namespace
            exec(current_code, namespace)
            
            # Ensure we return the DataFrame from the namespace
            if 'df' in namespace and isinstance(namespace['df'], pd.DataFrame):
                return namespace['df']
            else:
                raise ValueError("Code execution did not produce a valid DataFrame")
                
        except Exception as e:
            error_message = str(e)
            print(f"Error (attempt {attempt}): {error_message}")
            
            # Add to error history
            error_entry = {
                "attempt": attempt,
                "error": error_message,
                "code": current_code
            }
            error_history.append(error_entry)
            
            if attempt < max_attempts:
                # Prepare error history context
                error_context_str = str(error_context) if error_context else ""
                for entry in error_history:
                    error_context_str += f"\nAttempt {entry['attempt']}:\n"
                    error_context_str += f"Code: {entry['code']}\n"
                    error_context_str += f"Error: {entry['error']}\n"
                
                # Create debugging prompt with context
                prompt = f"""
                Current Error: {e}
                Current Code: {current_code}
                
                Error History:
                {error_context_str}
                
                Info about the date column:
                {df[date_column].unique() if isinstance(df, pd.DataFrame) else 'DataFrame not available'}
                
                Please fix the code to make it run successfully. The code must return a DataFrame by assigning it to the 'df' variable.
                """
                
                # Initialize the debug agent
                agent_debug = Agent(name="Debug Agent", instructions=DEBUG_PROMPT_DASHBOARD, model="gpt-4.1-mini-2025-04-14", output_type=str)
                
                # Run the debug agent
                result = await Runner.run(agent_debug, prompt)
                formatted_code = result.final_output
                
                # Extract code from AI response
                if "```python" in formatted_code:
                    current_code = formatted_code.split("```python")[1].split("```")[0].strip()
                elif "```" in formatted_code:
                    current_code = formatted_code.split("```")[1].split("```")[0].strip()
                else:
                    current_code = formatted_code
                
                print(f"AI suggested fix (attempt {attempt}):")
                print(current_code)
            else:
                print(f"Max attempts reached. Last error: {error_message}")
                raise ValueError(f"Failed to execute code after {max_attempts} attempts: {error_message}")
    
    # This should never be reached due to the raise in the else clause above
    raise ValueError("Unexpected execution path reached")

async def get_dashboard_filters(df:pd.DataFrame):
    '''
    This function will be used to get the filters for the dashboard.

    Args:
        df (pd.DataFrame): The dataframe to get the filters of
        
    Returns:
        dict: The filters for the dashboard
        
    '''
    try:
        columns=df.columns.tolist()
        #Remove columns with int or float datatype
        columns=[column for column in columns if df[column].dtype not in ["int64","float64","int32","float32"]]
        #Check for date column we can use a regex/string operation to check for date column(but it can be called something else also(example:timestamp) we will use a llm to check for date column)
        prompt=DATE_FINDER_PROMPT+"Here are the columns of the dataframe: "+str(columns)
        agent_date_finder=Agent(name="Date Finder",instructions=DATE_FINDER_PROMPT,model="gpt-4.1-mini-2025-04-14",output_type=date_finder_schema)
        date_finder_result=await Runner.run(agent_date_finder,prompt)
        date_column=date_finder_result.final_output.date_column        

        #Incase our llm has been able to find a date column
        if date_column != "No":
            try:
                #Look for that column in the dataframe
                if date_column in df.columns:
                    #convert it into pandas datetime column
                    df[date_column]=pd.to_datetime(df[date_column])
                    #Create a month year column with format Jan-2025 instead of 01-2025
                    df["month_year"]=df[date_column].dt.strftime('%b-%Y')

            except Exception as e:
                #For some reason the date_column processing has failed,but a date column was found
                #extarct 50 unique values from the date column
                unique_values=df[date_column].unique()[:50]
                prompt=DATE_COLUMN_PROCESSOR_PROMPT+"Error: "+str(e)+"Unique Values: "+str(unique_values)+"Date column in the dataframe to consider: "+date_column
                agent_date_column_processor=Agent(name="Date Column Processor",instructions=DATE_COLUMN_PROCESSOR_PROMPT,model="gpt-4.1-mini-2025-04-14")
                code=await Runner.run(agent_date_column_processor,prompt)
                #Extract the python code from the agent
                clean_python_code = code.final_output.replace("```python", "").replace("```", "")
                print("Here is the code that will be executed: by the llm in try 0\n")
                print(clean_python_code)
                #Create a namespace for the python code
                namespace = {"df": df, "pd": pd, "np": np}
                #Execute the code with debugging
                df=await execute_with_debug(clean_python_code, namespace, e, df,date_column)


        #now find filters for the dashboard
        prompt_filter=FILTER_PROMPT+"Here are the columns of the dataframe: "+str(columns)
        agent_filter=Agent(name="Filter",instructions=FILTER_PROMPT,model="gpt-4.1-mini-2025-04-14",output_type=filter_schema)
        filter_result=await Runner.run(agent_filter,prompt_filter)
        filters=filter_result.final_output.filters

        return filters,date_column,df
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

