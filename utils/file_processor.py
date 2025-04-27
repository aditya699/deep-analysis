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
        
        # Add the analysis task to background tasks
        if background_tasks is not None:
            background_tasks.add_task(
                run_analysis,
                task_id=task_id,
                file_url=blob_client.url,
                client=client
            )
        
        # Return task information
        return {
            "message": f"File {file.filename} uploaded successfully. Analysis started.",
            "task_id": task_id,
            "status": "pending",
            "file_url": blob_client.url
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")

async def run_analysis(task_id: str, file_url: str, client):
    """
    Run the data analysis process in the background
    
    Args:
        task_id: The unique identifier for this analysis task
        file_url: URL to the uploaded file in blob storage
        client: MongoDB client
    """
    try:
        # Get the database and collections
        db = client["Python-Data-Analyst"]
        tasks_collection = db["analysis_tasks"]
        
        # Update task status to "processing"
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "processing",
                "progress": 0.1,
                "message": "Starting analysis...",
                "updated_at": datetime.now()
            }}
        )
        
        # Download the file from blob storage
        # We need to download it since our analysis code expects a local file
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
        
        # Create a temporary directory if it doesn't exist
        os.makedirs("temp", exist_ok=True)
        local_file_path = f"temp/{blob_name.split('/')[-1]}"
        
        # Download the blob
        with open(local_file_path, "wb") as file:
            file.write(blob_client.download_blob().readall())
        
        # Update task status
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "progress": 0.2,
                "message": "File downloaded, loading data...",
                "updated_at": datetime.now()
            }}
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
        result, columns, prompt = await load_data(local_file_path, client)
        
        # Update task status
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "progress": 0.3,
                "message": "Data loaded, identifying KPIs...",
                "updated_at": datetime.now()
            }}
        )
        
        # Get KPIs
        kpi_names = await get_kpi(prompt, client)
        
        # Update task with identified KPIs
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "identified_kpis": kpi_names,
                "updated_at": datetime.now()
            }}
        )
        
        # Initialize master data dictionary
        master_data_dictionary = {}
        insights_master = ""
        
        # Process each KPI
        total_kpis = len(kpi_names)
        for index, kpi_name in enumerate(kpi_names):
            current_progress = 0.3 + (0.6 * (index / total_kpis))
            
            # Update task status when starting KPI
            await tasks_collection.update_one(
                {"task_id": task_id},
                {"$set": {
                    "progress": current_progress,
                    "message": f"Analyzing KPI: {kpi_name}",
                    "current_kpi": kpi_name,
                    "updated_at": datetime.now()
                }}
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
            
            # Update task with visualization URL
            if visualization["status"] == "success" and "visualization_url" in visualization:
                await tasks_collection.update_one(
                    {"task_id": task_id},
                    {"$set": {
                        "progress": current_progress + 0.3 * (1/total_kpis),
                        "message": f"Generated visualization for: {kpi_name}",
                        "updated_at": datetime.now(),
                        f"partial_results.{kpi_name}.visualization_url": visualization["visualization_url"]
                    }}
                )
            
            # Generate insights for the KPI
            insights = await get_analysis_insights(kpi_name, client, analysis, visualization["visualization_url"])
            master_data_dictionary[kpi_name]["insights"] = insights
            insights_master += insights
            
            # Update task with insights
            await tasks_collection.update_one(
                {"task_id": task_id},
                {"$set": {
                    "progress": current_progress + 0.6 * (1/total_kpis),
                    "message": f"Generated business insights for: {kpi_name}",
                    "updated_at": datetime.now(),
                    f"partial_results.{kpi_name}.insights": insights
                }}
            )
        
        # Generate summary of insights
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "progress": 0.9,
                "message": "Generating summary...",
                "updated_at": datetime.now()
            }}
        )
        
        summary = await get_insights_from_openai(insights_master, client)
        master_data_dictionary["summary"] = summary
        
        # Update with summary
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "progress": 0.95,
                "message": "Summary generated, creating final report...",
                "updated_at": datetime.now(),
                "summary": summary
            }}
        )
        
        # Save the master data dictionary to a json file
        os.makedirs("reports", exist_ok=True)
        data_file_path = f"reports/data_{task_id}.json"
        with open(data_file_path, "w") as f:
            json.dump(master_data_dictionary, f)
        
        # Generate HTML report
        report_file_path = f"reports/report_{task_id}.html"
        create_html_report(master_data_dictionary, output_filename=report_file_path)
        
        # Upload the report to blob storage
        container_client = blob_service_client.get_container_client("images-analysis")
        blob_client = container_client.get_blob_client(f"report_{task_id}.html")
        
        with open(report_file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        
        # Get the report URL
        report_url = blob_client.url
        
        # Update task status to completed
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "completed",
                "progress": 1.0,
                "message": "Analysis completed successfully",
                "report_url": report_url,
                "raw_data_url": data_file_path,  # Local path for now
                "updated_at": datetime.now()
            }}
        )
        
        # Clean up temporary file
        os.remove(local_file_path)

        # Clean up the report file
        os.remove(report_file_path)

        # Clean up the master data dictionary file
        os.remove(data_file_path)
        
        # Delete the charts folder if it exists
        if os.path.exists("charts") and os.path.isdir("charts"):
            import shutil
            shutil.rmtree("charts")
            
    except Exception as e:
        # Log the error
        error_detail = str(e)
        error_traceback = traceback.format_exc()
        
        # Update task status to failed
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "failed",
                "message": f"Analysis failed: {error_detail}",
                "error_detail": error_detail,
                "error_traceback": error_traceback,
                "updated_at": datetime.now()
            }}
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