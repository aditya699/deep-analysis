from fastapi import UploadFile, HTTPException, BackgroundTasks
from database.get_client import get_client
from azure.storage.blob import BlobServiceClient # type: ignore
import os
import uuid
from datetime import datetime
from dotenv import load_dotenv
import traceback
import json
import matplotlib
# Set matplotlib to use Agg backend to avoid Tkinter threading issues
matplotlib.use('Agg')
load_dotenv()

async def process_uploaded_file(file: UploadFile, background_tasks: BackgroundTasks = None):
    """
    Process an uploaded CSV file and start the analysis in the background
    """
    try:
        # Read file content
        file_content = await file.read()
        if not file_content:
            raise ValueError("Uploaded file is empty")
            
        # Check if environment variable exists
        connection_string = os.getenv("BLOB_STORAGE_ACCOUNT_KEY")
        if not connection_string:
            raise ValueError("BLOB_STORAGE_ACCOUNT_KEY environment variable is not set")
            
        # Create a blob client and MongoDB client
        client = await get_client() 
        db = client["Python-Data-Analyst"]
        logs_collection = db["logs"]
        tasks_collection = db["analysis_tasks"]  # Collection for tracking tasks
        
        # Connect to blob storage
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        container_client = blob_service_client.get_container_client("images-analysis")
        
        # Create a unique filename
        file_id = str(uuid.uuid4())
        unique_filename = file_id
    
        # Upload the file to blob storage
        blob_client = container_client.get_blob_client(unique_filename)
        blob_client.upload_blob(file_content)
        
        # Create metadata
        file_metadata = {
            "filename": file.filename,
            "unique_filename": unique_filename,
            "file_size": len(file_content),
            "upload_date": datetime.now().isoformat(),
            "blob_url": blob_client.url,
            "type": "File Information"
        }
        
        # Log file upload
        await logs_collection.insert_one(file_metadata)
        
        # Create a task ID for the analysis
        task_id = str(uuid.uuid4())
        
        # Create task tracking document
        task_document = {
            "task_id": task_id,
            "file_id": file_id,
            "file_url": blob_client.url,
            "status": "pending",
            "progress": 0.0,
            "message": "Analysis queued",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "report_url": None,
            "raw_data_url": None
        }
        
        # Insert task document
        await tasks_collection.insert_one(task_document)
        
        # we need to add the task to the redis queue
        from utils.redis_tasks import enqueue_task
        await enqueue_task(task_id,blob_client.url)

     
        
        # Return task information
        return {
            "message": f"File {file.filename} uploaded successfully. Analysis queued.",
            "task_id": task_id,
            "status": "pending",
            "file_url": blob_client.url
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
        

async def update_task_progress(task_id: str, status: str, progress: float, message: str, additional_data: dict = None):
    """
    Simplified update task progress function - focuses only on clean updates to MongoDB
    """
    try:
        # Get the database client
        client = await get_client()
        db = client["Python-Data-Analyst"]
        tasks_collection = db["analysis_tasks"]
        
        # Create base update data with simple top-level fields
        update_data = {
            "status": status,
            "progress": progress,
            "message": message,
            "updated_at": datetime.now()
        }
        
        # Special handling for identified_kpis to ensure consistency
        if additional_data and "identified_kpis" in additional_data:
            kpi_names = additional_data["identified_kpis"]
            update_data["identified_kpis"] = kpi_names
            
            # Initialize partial_results structure if needed
            partial_results = {}
            for kpi in kpi_names:
                partial_results[kpi] = {
                    "visualization_url": None,
                    "insights": None
                }
            update_data["partial_results"] = partial_results
            
            # Remove from additional_data to prevent double-processing
            additional_data.pop("identified_kpis")
        
        # Handle updates to partial_results directly
        if additional_data and "partial_results" in additional_data:
            # Get the current document to merge with existing partial_results
            current_doc = await tasks_collection.find_one({"task_id": task_id})
            if current_doc and "partial_results" in current_doc:
                # Start with existing partial_results
                merged_results = current_doc["partial_results"].copy()
                
                # Update with new values
                for kpi, data in additional_data["partial_results"].items():
                    if kpi not in merged_results:
                        merged_results[kpi] = {"visualization_url": None, "insights": None}
                    
                    # Update specific fields
                    for field, value in data.items():
                        merged_results[kpi][field] = value
                
                update_data["partial_results"] = merged_results
            else:
                # No existing partial_results, use the provided one directly
                update_data["partial_results"] = additional_data["partial_results"]
                
            # Remove from additional_data to prevent double-processing
            additional_data.pop("partial_results")
        
        # Add any remaining additional data directly to the update
        if additional_data:
            for key, value in additional_data.items():
                update_data[key] = value
        
        # Update MongoDB using a single $set operation
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": update_data}
        )
        
        return True
    except Exception as e:
        print(f"Error updating task progress: {e}")
        return False


async def run_analysis(task_id: str, file_url: str, client):
    """
    Run the data analysis process in the background
    """
    try:
        # Get the database and collections
        db = client["Python-Data-Analyst"]
        tasks_collection = db["analysis_tasks"]
        
        # Update task status to "processing"
        await update_task_progress(
            task_id,
            "processing",
            0.1,
            "Starting analysis..."
        )
        
        # Download the file from blob storage
        connection_string = os.getenv("BLOB_STORAGE_ACCOUNT_KEY")
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        
        # Extract the container name and blob name from the URL
        from urllib.parse import urlparse
        parsed_url = urlparse(file_url)
        path_parts = parsed_url.path.strip('/').split('/')
        container_name = path_parts[0]
        blob_name = '/'.join(path_parts[1:])
        
        # Get the blob client
        blob_client = blob_service_client.get_blob_client(
            container=container_name,
            blob=blob_name
        )
        
        # Update task status
        await update_task_progress(
            task_id,
            "processing",
            0.2,
            "File downloaded, loading data..."
        )
        
        # Import our analysis functions
        from utils.services import (
            load_data, 
            get_kpi, 
            get_analysis, 
            get_analysis_insights, 
            get_visualization,
            get_insights_from_openai
        )
        from utils.html_report_generator import create_html_report
        
        # Load data
        result, columns, prompt = await load_data(file_url, client)
        
        # Update task status
        await update_task_progress(
            task_id,
            "processing",
            0.3,
            "Data loaded, identifying KPIs..."
        )
        
        # Get KPIs
        kpi_names = await get_kpi(prompt, client)
        
        # Update task with identified KPIs and initialize partial_results
        await update_task_progress(
            task_id,
            "processing",
            0.3,
            "KPIs identified",
            {
                "identified_kpis": kpi_names
            }
        )
        
        # Initialize master data dictionary
        master_data_dictionary = {}
        insights_master = ""
        
        # Process each KPI
        total_kpis = len(kpi_names)
        for index, kpi_name in enumerate(kpi_names):
            current_progress = 0.3 + (0.6 * (index / total_kpis))
            
            try:
                # Update task status when starting KPI
                await update_task_progress(
                    task_id,
                    "processing",
                    current_progress,
                    f"Analyzing KPI: {kpi_name}",
                    {
                        "current_kpi": kpi_name
                    }
                )
                
                # Get analysis for the KPI
                analysis = await get_analysis(kpi_name, prompt, client, result)
                
                # Initialize the dictionary entry for this KPI
                if kpi_name not in master_data_dictionary:
                    master_data_dictionary[kpi_name] = {}
                
                master_data_dictionary[kpi_name]["raw_response"] = analysis
                
                # Get visualization for the KPI
                visualization = await get_visualization(kpi_name, prompt, client, result, blob_service_client)
                master_data_dictionary[kpi_name]["visualization"] = visualization
                
                # Update task with visualization URL if successful
                if visualization["status"] == "success" and "visualization_url" in visualization:
                    await update_task_progress(
                        task_id,
                        "processing",
                        current_progress + 0.3 * (1/total_kpis),
                        f"Generated visualization for: {kpi_name}",
                        {
                            "partial_results": {
                                kpi_name: {
                                    "visualization_url": visualization["visualization_url"]
                                }
                            }
                        }
                    )
                
                # Generate insights for the KPI
                insights = await get_analysis_insights(kpi_name, client, analysis, visualization.get("visualization_url"))
                master_data_dictionary[kpi_name]["insights"] = insights
                insights_master += insights
                
                # Update task with insights
                await update_task_progress(
                    task_id,
                    "processing",
                    current_progress + 0.6 * (1/total_kpis),
                    f"Generated business insights for: {kpi_name}",
                    {
                        "partial_results": {
                            kpi_name: {
                                "insights": insights
                            }
                        }
                    }
                )
            except Exception as e:
                # Log the error but continue with next KPI
                print(f"Error processing KPI '{kpi_name}': {e}")
                
                # Update partial results to mark this KPI as having an error
                await update_task_progress(
                    task_id,
                    "processing",
                    current_progress,
                    f"Error analyzing KPI: {kpi_name}",
                    {
                        "partial_results": {
                            kpi_name: {
                                "error": str(e)
                            }
                        }
                    }
                )
                
                # Continue with the next KPI
                continue
        
        # Generate summary of insights
        await update_task_progress(
            task_id,
            "processing",
            0.9,
            "Generating summary..."
        )
        
        summary = await get_insights_from_openai(insights_master, client)
        master_data_dictionary["summary"] = summary
        
        # Update with summary
        await update_task_progress(
            task_id,
            "processing",
            0.95,
            "Summary generated, creating final report...",
            {"summary": summary}
        )
        
        # Save the master data dictionary to a json file
        os.makedirs("reports", exist_ok=True)
        data_file_path = f"reports/data_{task_id}.json"
        
        # Upload JSON data directly to blob storage
        container_client = blob_service_client.get_container_client("images-analysis")
        json_blob_client = container_client.get_blob_client(f"data_{task_id}.json")
        json_blob_client.upload_blob(json.dumps(master_data_dictionary).encode('utf-8'), overwrite=True)
        json_data_url = json_blob_client.url

        # Generate HTML content in memory
        html_content = create_html_report(master_data_dictionary)

        # Upload HTML content directly to blob storage
        html_blob_client = container_client.get_blob_client(f"report_{task_id}.html")
        html_blob_client.upload_blob(html_content.encode('utf-8'), overwrite=True)
        report_url = html_blob_client.url

        # Update task status to completed with URLs to both files
        await update_task_progress(
            task_id,
            "completed",
            1.0,
            "Analysis completed successfully",
            {
                "report_url": report_url,
                "raw_data_url": json_data_url
            }
        )

        # Clean up the master data dictionary file
        if os.path.exists(data_file_path):
            os.remove(data_file_path)   
        
        # Delete the charts folder if it exists
        if os.path.exists("charts") and os.path.isdir("charts"):
            import shutil
            shutil.rmtree("charts")
            
    except Exception as e:
        # Log the error
        error_detail = str(e)
        error_traceback = traceback.format_exc()
        
        # Update task status to failed in MongoDB
        await update_task_progress(
            task_id,
            "failed",
            0,
            f"Analysis failed: {error_detail}",
            {
                "error_detail": error_detail,
                "error_traceback": error_traceback
            }
        )

async def get_task_status_from_db(task_id: str):
    """
    Get the current status of a task from MongoDB
    """
    try:
        client = await get_client()
        db = client["Python-Data-Analyst"]
        tasks_collection = db["analysis_tasks"]
        
        task = await tasks_collection.find_one({"task_id": task_id})
        
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        # Convert MongoDB ObjectId to string for JSON serialization
        task["_id"] = str(task["_id"])
        
        return task
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Error retrieving task status: {str(e)}")