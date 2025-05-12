'''
Note:
1.We will not be logging tokens usage since openai is already logging it, in a nice way.In future we might need a custom logging system.
'''

from contextlib import redirect_stdout
from io import StringIO
import pandas as pd
import numpy as np
import os
from database.get_client import get_client
from fastapi import Request,HTTPException
from datetime import datetime
from utils.prompts import MANAGER_PROMPT,DATA_ANALYST,DEBUG_PROMPT,BUSINESS_ANALYST,VISUALIZER_PROMPT,SUMMARY_PROMPT
from agents import Agent,Runner
from utils.schemas import KPI
from dotenv import load_dotenv
import uuid
from openai import OpenAI

load_dotenv()

os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

async def load_data(file_path_or_url: str, client: Request):
    """
    This function is used to load data from either a CSV file or a blob URL.

    Args:
        file_path_or_url: str - Either a local file path or a blob URL
        client: Request

    Returns:
        df: pd.DataFrame
        columns: list
        prompt: str
    """
    # Check if the input is a URL or a local path
    if file_path_or_url.startswith('http'):
        # It's a blob URL, so read directly from the blob
        import requests
        from io import BytesIO
        
        try:
            # Download content from blob URL directly
            response = requests.get(file_path_or_url)
            response.raise_for_status()  # Raise exception for 4XX/5XX responses
            
            # Read content directly into pandas using BytesIO
            file_content = BytesIO(response.content)
            df = pd.read_csv(file_content)
            columns = df.columns.tolist()
            
            if len(columns) == 0:
                return HTTPException(status_code=500, detail="No columns found in the file, dataset unfit for analysis")
            
            # Generate prompt with dataset information
            prompt = f"Here is the dataset description:\n"
            for column in columns:
                prompt += f"Column Name: {column}\n"
                prompt += f"Null Values: {df[column].isnull().sum()}\n"
                prompt += f"Data Type: {df[column].dtype}\n"
                unique_values = df[column].unique().tolist()
                num_to_show = min(20, len(unique_values))
                prompt += f"Top {num_to_show} Unique Values: {unique_values[:num_to_show]}\n"
                prompt += f"Number of Unique Values: {len(df[column].unique())}\n"
            
            # Log to database
            db = client['Python-Data-Analyst']
            collection = db['logs']
            dict = {
                "timestamp": datetime.now(),
                "file_path_or_url": file_path_or_url,
                "columns": columns,
                "message": "Data loaded successfully from blob URL",
                "prompt": prompt
            }
            await collection.insert_one(dict)
            
            return df, columns, prompt
            
        except Exception as e:
            print(f"Error loading data from blob URL: {e}")
            return HTTPException(status_code=500, detail=f"Error loading data from blob URL: {e}")
    
    else:
        # It's a local file path, use the original method
        encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
        
        for encoding in encodings:
            try:
                df = pd.read_csv(file_path_or_url, encoding=encoding)
                columns = df.columns.tolist()

                if len(columns) == 0:
                    return HTTPException(status_code=500, detail="No columns found in the file, dataset unfit for analysis")

                db = client['Python-Data-Analyst']
                collection = db['logs']

                prompt = f"Here is the dataset description:\n"

                for column in columns:
                    prompt += f"Column Name: {column}\n"
                    prompt += f"Null Values: {df[column].isnull().sum()}\n"
                    prompt += f"Data Type: {df[column].dtype}\n"
                    unique_values = df[column].unique().tolist()
                    num_to_show = min(20, len(unique_values))
                    prompt += f"Top {num_to_show} Unique Values: {unique_values[:num_to_show]}\n"
                    prompt += f"Number of Unique Values: {len(df[column].unique())}\n"  

                dict = {
                    "timestamp": datetime.now(),
                    "file_path": file_path_or_url,
                    "encoding": encoding,
                    "columns": columns,
                    "message": "Data loaded successfully from local file",
                    "prompt": prompt
                }

                await collection.insert_one(dict) 
                return df, columns, prompt
                
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"Error loading data from local file: {e}")
                return HTTPException(status_code=500, detail=f"Error loading data from local file: {e}")
        
        print(f"Could not read file with any of the attempted encodings")
        return HTTPException(status_code=500, detail="Could not read file with any of the attempted encodings")

async def get_kpi(prompt:str,client:Request)->list:
    """
    This function will be talking to the manager agent to get the set of kpi's

    Args:
        prompt:str(This is detailed dataset description)
        client:Request

    Returns:
        list
    """
    try:
        #Initialize the manager agent
        agent_manager = Agent(name="Manager", instructions=MANAGER_PROMPT, model="gpt-4.1-mini-2025-04-14", output_type=KPI)

        #Run the manager agent
        kpi_result = await Runner.run(agent_manager,prompt)

        #Extract the kpi names from the kpi result
        kpi_names = kpi_result.final_output.kpi_names[:3]

        #Filter two kpi names for testing
        # kpi_names = kpi_names[:2]

        db = client['Python-Data-Analyst']
        collection = db['logs']

        dict={
            "timestamp":datetime.now(),
            "prompt":prompt,
            "kpi_names":kpi_names,
            "message":"KPI's extracted successfully(get_kpi)"
        }
        #Insert the kpi names into the database
        await collection.insert_one(dict)

        #Return the kpi names
        return kpi_names
    except Exception as e:
        print(f"Error getting kpi: {e}")
        dict={
            "timestamp":datetime.now(),
            "prompt":prompt,
            "message":f"Error getting kpi: {e}",
            "class":"get_kpi",
            "type":"error"
        }
        await collection.insert_one(dict)
        return HTTPException(status_code=500, detail=f"Error getting kpi: {e}")
  

async def execute_with_debug(code, namespace, kpi_name, dataset_prompt, client:Request, max_attempts=3):
    """
    Execute code with debugging capabilities, retrying up to max_attempts times.
    
    Args:
        code: The Python code to execute
        namespace: The namespace for execution
        kpi_name: Name of the KPI being processed
        dataset_prompt: Description of the dataset
        client: Database client
        max_attempts: Maximum number of debugging attempts
        
    Returns:
        The successfully executed code or the last attempted version
    """
    agent_debug = Agent(name="Debug Agent", instructions=DEBUG_PROMPT, model="gpt-4.1-mini-2025-04-14", output_type=str)
    error_history = []  # Store error history for context
    current_code = code
    
    db = client['Python-Data-Analyst']
    collection = db['logs']
    
    for attempt in range(1, max_attempts + 1):
        try:
            exec(current_code, namespace)
            print(f"Code for '{kpi_name}' executed successfully.")
            
            # Log successful execution
            await collection.insert_one({
                "timestamp": datetime.now(),
                "kpi_name": kpi_name,
                "attempt": attempt,
                "status": "success",
                "code": current_code,
                "message": f"Code executed successfully on attempt {attempt}"
            })
            
            return current_code  # Return the successful code
        except Exception as e:
            error_message = str(e)
            print(f"Error in '{kpi_name}' (attempt {attempt}): {error_message}")
            
            # Add to error history
            error_entry = {
                "attempt": attempt,
                "error": error_message,
                "code": current_code,
                "kpi": kpi_name
            }
            error_history.append(error_entry)
            
            # Log error to database
            await collection.insert_one({
                "timestamp": datetime.now(),
                "kpi_name": kpi_name,
                "attempt": attempt,
                "status": "error",
                "error": error_message,
                "code": current_code,
                "message": f"Error on attempt {attempt}: {error_message}"
            })
            
            if attempt < max_attempts:
                # Prepare error history context
                error_context = ""
                for entry in error_history:
                    error_context += f"Attempt {entry['attempt']} for KPI '{entry['kpi']}':\n"
                    error_context += f"Code: {entry['code']}\n"
                    error_context += f"Error: {entry['error']}\n\n"
                
                # Create debugging prompt with context
                prompt = f"""
                Current Error: {e}
                Current Code: {current_code}
                Current KPI: {kpi_name}
                
                Error History:
                {error_context}
                
                Dataset: {dataset_prompt}
                
                Please fix the code to make it run successfully.
                """
                
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
                
                # Log the AI fix attempt
                await collection.insert_one({
                    "timestamp": datetime.now(),
                    "kpi_name": kpi_name,
                    "attempt": attempt,
                    "status": "debug",
                    "original_code": error_entry["code"],
                    "fixed_code": current_code,
                    "error": error_message,
                    "message": f"AI suggested fix for attempt {attempt}"
                })
            else:
                print(f"Max attempts reached for '{kpi_name}'. Moving on.")
                
                # Log max attempts reached
                await collection.insert_one({
                    "timestamp": datetime.now(),
                    "kpi_name": kpi_name,
                    "status": "max_attempts_reached",
                    "final_code": current_code,
                    "message": f"Max debugging attempts ({max_attempts}) reached for KPI '{kpi_name}'"
                })
                
                return current_code  # Return the last code version
    
    return current_code

async def get_analysis(kpi_name:str, dataset_prompt:str, client:Request, df:pd.DataFrame)->str:
    """
    This function will be talking to the data analyst agent to get the analysis for the given kpi

    Args:
        kpi_name: str - The KPI to analyze
        client: Request - Database client
        df: pd.DataFrame - The dataframe to analyze

    Returns:
        str - The analysis result
    """
    db = client['Python-Data-Analyst']
    collection = db['logs']
    
    try:
        f1 = StringIO()
        # Initialize the data analyst agent
        agent_data_analyst = Agent(name="Data Analyst", instructions=DATA_ANALYST, model="gpt-4.1-mini-2025-04-14", output_type=str)
        prompt=f"Here is the dataset description:\n{dataset_prompt}\n\nHere is the KPI to analyze:\n{kpi_name}"
        # Run the data analyst agent
        analysis_result = await Runner.run(agent_data_analyst, prompt)
        
        # Log agent response received
        await collection.insert_one({
            "timestamp": datetime.now(),
            "kpi_name": kpi_name,
            "status": "agent_response_received",
            "raw_response": analysis_result.final_output,
            "message": "Received analysis from Data Analyst agent"
        })

        clean_python_code = analysis_result.final_output.replace("```python", "").replace("```", "")
        # Create a namespace for the python code
        namespace = {"df": df, "pd": pd, "np": np}

        # Execute with debugging and capture output
        with redirect_stdout(f1):
            debugged_code = await execute_with_debug(clean_python_code, namespace, kpi_name, dataset_prompt, client)
        
        output = f1.getvalue()

        # Log successful analysis
        analysis_log = {
            "timestamp": datetime.now(),
            "kpi_name": kpi_name,
            "status": "success",
            "analysis": analysis_result.final_output,
            "execution_output": output,
            "final_code": debugged_code,
            "message": "Analysis generated successfully"
        }
        await collection.insert_one(analysis_log)

        # Return the analysis
        return output
    except Exception as e:
        error_message = str(e)
        print(f"Error getting analysis: {error_message}")
        
        # Log error
        error_log = {
            "timestamp": datetime.now(),
            "kpi_name": kpi_name,
            "status": "error",
            "error": error_message,
            "class": "get_analysis",
            "type": "error",
            "message": f"Error getting analysis: {error_message}"
        }
        await collection.insert_one(error_log)
        
        return HTTPException(status_code=500, detail=f"Error getting analysis: {error_message}")

async def get_analysis_insights(kpi_name:str, client:Request, analysis_result:str, visualization_url:str=None)->str:
    """
    This function will be talking to the business analyst agent to get the insights for the given kpi
    using both text analysis and visualization image if available

    Args:
        kpi_name: str - The KPI to analyze
        client: Request - Database client
        analysis_result: str - The analysis result to get insights from
        visualization_url: str - Optional URL to the visualization image

    Returns:
        str - The insights
    """
    db = client['Python-Data-Analyst']
    collection = db['logs']
    
    try:
        openai_client = OpenAI()
        
        # Prepare content based on whether we have an image or not
        content = [
            { "type": "input_text", "text": BUSINESS_ANALYST + f"Here is the KPI to analyze:\n{kpi_name}\n\nHere is the analysis result:\n{analysis_result}" }
        ]
        
        # Add image to content if available
        if visualization_url:
            content.append({
                "type": "input_image",
                "image_url": visualization_url
            })
            
        # Create the response using OpenAI client with multimodal input
        response = openai_client.responses.create(
            model="gpt-4.1-mini-2025-04-14",
            input=[
                {
                    "role": "user",
                    "content": content
                }
            ]
        )
        
        # Extract just the text content from the response
        insights_text = response.output[0].content[0].text if response.output else "No insights generated"
        
        # Log successful insights generation
        await collection.insert_one({
            "timestamp": datetime.now(),
            "kpi_name": kpi_name,
            "status": "success",
            "insights": insights_text,
            "visualization_included": visualization_url is not None,
            "message": "Business insights generated successfully with multimodal input"
        })
        
        return insights_text
    except Exception as e:
        error_message = str(e)
        print(f"Error getting analysis insights: {error_message}")
        
        # Log error
        await collection.insert_one({
            "timestamp": datetime.now(),
            "kpi_name": kpi_name,
            "status": "error",
            "error": error_message,
            "class": "get_analysis_insights",
            "type": "error",
            "visualization_included": visualization_url is not None,
            "message": f"Error getting analysis insights: {error_message}"
        })
        
        return HTTPException(status_code=500, detail=f"Error getting analysis insights: {error_message}")

def sanitize_kpi_name(kpi_name: str) -> str:
    """
    Sanitizes a KPI name by removing special characters and replacing spaces with underscores.
    
    Args:
        kpi_name: str - The original KPI name
        
    Returns:
        str - Sanitized KPI name safe for filenames
    """
    # Replace special characters with underscores
    sanitized = ''.join(c if c.isalnum() or c.isspace() else '_' for c in kpi_name)
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Remove multiple consecutive underscores
    sanitized = '_'.join(filter(None, sanitized.split('_')))
    return sanitized

async def get_visualization(kpi_name:str, dataset_prompt:str, client:Request, df:pd.DataFrame, blob_client:Request)->dict:
    """
    This function will be talking to the visualization agent to get the visualization for the given kpi
    
    Args:
        kpi_name: str - The KPI to visualize
        dataset_prompt: str - Dataset description
        client: Request - Database client
        df: pd.DataFrame - The dataframe to visualize
        blob_client: Request - Azure blob storage client
        
    Returns:
        dict - Contains the file path of the saved visualization
    """
    db = client['Python-Data-Analyst']
    collection = db['logs']
    
    try:
        f1 = StringIO()
        unique_id = str(uuid.uuid4())
        # Sanitize the KPI name before using it in the filename
        sanitized_kpi_name = sanitize_kpi_name(kpi_name)
        file_name = f"{sanitized_kpi_name}_{unique_id}.png"
        container_name = "images-analysis"
        
        # Initialize the visualization agent
        agent_visualization = Agent(name="Visualization Agent", instructions=VISUALIZER_PROMPT, model="gpt-4.1-mini-2025-04-14", output_type=str)
        prompt = f"Here is the KPI to analyze:\n{kpi_name}\n\nHere is the dataset description:\n{dataset_prompt}"
        
        # Generate the visualization code
        visualization_result = await Runner.run(agent_visualization, prompt)
        
        # Clean the code
        clean_python_code = visualization_result.final_output
        if "```python" in clean_python_code:
            clean_python_code = clean_python_code.split("```python")[1].split("```")[0].strip()
        elif "```" in clean_python_code:
            clean_python_code = clean_python_code.split("```")[1].split("```")[0].strip()
            
        # Remove plt.show() if it exists as it can block the backend
        clean_python_code = clean_python_code.replace("plt.show()", "")

        clean_python_code = clean_python_code.replace("plt.savefig", "# plt.savefig")
            
        # Add code to save figure to blob storage
        save_code = f"\n# Save figure to blob storage\nplt.savefig('{file_name}')\n"
        
        # Insert save_code before plt.close() if it exists, otherwise append it
        if "plt.close()" in clean_python_code:
            clean_python_code = clean_python_code.replace("plt.close()", f"{save_code}plt.close()")
        else:
            clean_python_code += save_code

        # Add matplotlib Agg backend to prevent tkinter threading issues
        matplotlib_import_line = "import matplotlib\nmatplotlib.use('Agg')\n"
        if "import matplotlib.pyplot" in clean_python_code and "matplotlib.use" not in clean_python_code:
            clean_python_code = clean_python_code.replace("import matplotlib.pyplot", f"{matplotlib_import_line}import matplotlib.pyplot")
        elif "import matplotlib" not in clean_python_code:
            clean_python_code = f"{matplotlib_import_line}{clean_python_code}"

        print(clean_python_code)

        # Create a namespace for the python code
        namespace = {"df": df, "pd": pd, "np": np}

        # Execute the code
        with redirect_stdout(f1):
            execution_result = await execute_with_debug(clean_python_code, namespace, kpi_name, dataset_prompt, client)
        
        # Upload the visualization to blob storage
        try:
            # Check if the file exists before trying to upload it
            if not os.path.exists(file_name):
                # Log the issue
                await collection.insert_one({
                    "timestamp": datetime.now(),
                    "kpi_name": kpi_name,
                    "status": "error",
                    "error": "Visualization file was not created",
                    "code": clean_python_code,
                    "message": "Failed to create visualization file"
                })
                
                # Return error info
                return {
                    "status": "error",
                    "message": "Could not generate visualization",
                    "kpi_name": kpi_name,
                    "visualization_url": None
                }
                
            container_client = blob_client.get_container_client(container_name)
            
            # Upload the file to blob storage
            blob_client = container_client.get_blob_client(file_name)
            with open(file_name, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            
            # Get the URL of the uploaded blob
            blob_url = blob_client.url
            
            # Remove the local file after uploading
            os.remove(file_name)
            
            # Log successful visualization
            await collection.insert_one({
                "timestamp": datetime.now(),
                "kpi_name": kpi_name,
                "status": "success",
                "visualization_url": blob_url,
                "final_code": execution_result,
                "message": "Visualization generated and uploaded successfully"
            })
            
            return {
                "status": "success",
                "visualization_url": blob_url,
                "kpi_name": kpi_name,
                "message": "Visualization generated successfully"
            }
            
        except Exception as e:
            error_message = str(e)
            print(f"Error uploading visualization to blob storage: {error_message}")
            
            # Log blob storage error
            await collection.insert_one({
                "timestamp": datetime.now(),
                "kpi_name": kpi_name,
                "status": "error",
                "error": error_message,
                "class": "get_visualization",
                "type": "blob_storage_error",
                "message": f"Error uploading visualization to blob storage: {error_message}"
            })
            
                    # Return error info instead of local file path
            return {
                "status": "error",
                "error": error_message,
                "kpi_name": kpi_name,
                "message": "Failed to upload visualization to blob storage",
                "visualization_url": None  # No URL available since upload failed
            }
                        
    except Exception as e:
        error_message = str(e)
        print(f"Error generating visualization: {error_message}")
        
        # Log error
        await collection.insert_one({
            "timestamp": datetime.now(),
            "kpi_name": kpi_name,
            "status": "error",
            "error": error_message,
            "class": "get_visualization",
            "type": "error",
            "message": f"Error generating visualization: {error_message}"
        })
        
        # Return error info instead of raising exception
        return {
            "status": "error",
            "error": error_message,
            "message": "Failed to generate visualization",
            "kpi_name": kpi_name,
            "visualization_url": None
        }

async def get_insights_from_openai(insights:str,client:Request)->str:
    """
    This function will be acting as a final agent for summary of insights

    Args:  
        insights: str - The insights to summarize
        client: Request - Database client

    Returns:
        str - The summary of insights
    """
    try:
        db = client['Python-Data-Analyst']
        collection = db['logs']
        
        summary_agent = Agent(name="Summary Agent", instructions=SUMMARY_PROMPT, model="gpt-4.1-mini-2025-04-14", output_type=str)
        summary_result = await Runner.run(summary_agent, insights)
        
        # Log successful summary generation
        await collection.insert_one({
            "timestamp": datetime.now(),
            "status": "success",
            "insights": insights,
            "summary": summary_result.final_output,
            "message": "Summary generated successfully"
        })
        
        return summary_result.final_output
    except Exception as e:
        error_message = str(e)
        print(f"Error getting insights from openai: {error_message}")
        
        # Log error
        await collection.insert_one({
            "timestamp": datetime.now(),
            "status": "error",
            "error": error_message,
            "class": "get_insights_from_openai",
            "type": "error",
            "message": f"Error getting insights from openai: {error_message}"
        })
        
        return HTTPException(status_code=500, detail=f"Error getting insights from openai: {error_message}")
