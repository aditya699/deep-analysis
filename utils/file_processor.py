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
            "message": f"File {file.filename} uploaded successfully. Analysis queued.",
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
        # Add Redis update with proper initialization
        await update_redis_task(
            task_id, 
            "processing", 
            0.1, 
            "Starting analysis...",
            {"partial_results": {}}  # Initialize empty partial_results
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
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "progress": 0.2,
                "message": "File downloaded, loading data...",
                "updated_at": datetime.now()
            }}
        )
        # Add Redis update
        await update_redis_task(task_id, "processing", 0.2, "File downloaded, loading data...")
        
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
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "progress": 0.3,
                "message": "Data loaded, identifying KPIs...",
                "updated_at": datetime.now()
            }}
        )
        # Add Redis update
        await update_redis_task(task_id, "processing", 0.3, "Data loaded, identifying KPIs...")
        
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
        # Add Redis update with KPIs and initialize partial_results structure
        await update_redis_task(
            task_id, 
            "processing", 
            0.3, 
            "KPIs identified",
            {
                "identified_kpis": kpi_names,
                "partial_results": {kpi: {} for kpi in kpi_names}  # Initialize structure for each KPI
            }
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
            # Add Redis update with current KPI
            await update_redis_task(
                task_id, 
                "processing", 
                current_progress, 
                f"Analyzing KPI: {kpi_name}",
                {"current_kpi": kpi_name}
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
                # MongoDB update
                await tasks_collection.update_one(
                    {"task_id": task_id},
                    {"$set": {
                        "progress": current_progress + 0.3 * (1/total_kpis),
                        "message": f"Generated visualization for: {kpi_name}",
                        "updated_at": datetime.now(),
                        f"partial_results.{kpi_name}.visualization_url": visualization["visualization_url"]
                    }}
                )
                # Redis update with properly structured data
                await update_redis_task(
                    task_id, 
                    "processing", 
                    current_progress + 0.3 * (1/total_kpis), 
                    f"Generated visualization for: {kpi_name}",
                    {f"partial_results.{kpi_name}.visualization_url": visualization["visualization_url"]}
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
            # Add Redis update with insights
            await update_redis_task(
                task_id, 
                "processing", 
                current_progress + 0.6 * (1/total_kpis), 
                f"Generated business insights for: {kpi_name}",
                {f"partial_results.{kpi_name}.insights": insights}
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
        # Add Redis update
        await update_redis_task(task_id, "processing", 0.9, "Generating summary...")
        
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
        # Add Redis update with summary
        await update_redis_task(
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
        await tasks_collection.update_one(
            {"task_id": task_id},
            {"$set": {
                "status": "completed",
                "progress": 1.0,
                "message": "Analysis completed successfully",
                "report_url": report_url,
                "raw_data_url": json_data_url,
                "updated_at": datetime.now()
            }}
        )
        # Add Redis update with URLs and final status
        await update_redis_task(
            task_id, 
            "completed", 
            1.0, 
            "Analysis completed successfully",
            {
                "report_url": report_url,
                "raw_data_url": json_data_url,
                "status": "completed",
                "progress": 1.0
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
        # Add Redis update with error details
        await update_redis_task(
            task_id, 
            "failed", 
            0, 
            f"Analysis failed: {error_detail}",
            {
                "error_detail": error_detail,
                "error_traceback": error_traceback,
                "status": "failed",
                "progress": 0
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
    

async def update_redis_task(task_id, status, progress, message, additional_data=None):
    """
    Update task status in Redis with proper handling of nested data
    """
    try:
        from utils.redis_tasks import redis_client
        import json
        from datetime import datetime
        
        # Get current task data with proper error handling
        task_data_str = await redis_client.get(f"task:{task_id}")
        if not task_data_str:
            task_data = {
                "task_id": task_id,
                "status": status,
                "progress": progress,
                "message": message,
                "updated_at": datetime.now().isoformat(),
                "partial_results": {}
            }
        else:
            try:
                task_data = json.loads(task_data_str)
            except json.JSONDecodeError as e:
                print(f"Error decoding Redis data for task {task_id}: {e}")
                task_data = {
                    "task_id": task_id,
                    "status": status,
                    "progress": progress,
                    "message": message,
                    "updated_at": datetime.now().isoformat(),
                    "partial_results": {}
                }
            
            # Update basic fields
            task_data["status"] = status
            task_data["progress"] = progress
            task_data["message"] = message
            task_data["updated_at"] = datetime.now().isoformat()
            
            # Ensure partial_results exists and is a dictionary
            if "partial_results" not in task_data or not isinstance(task_data["partial_results"], dict):
                task_data["partial_results"] = {}
        
        # Handle additional data updates
        if additional_data:
            # Track valid KPIs and their data
            valid_kpis = {}
            
            for key, value in additional_data.items():
                if key.startswith('partial_results.'):
                    # Handle nested partial_results updates
                    parts = key.split('.', 2)
                    if len(parts) >= 3:
                        kpi_name = parts[1]
                        property_name = parts[2]
                        
                        # Normalize KPI name to lowercase for consistency
                        normalized_kpi = kpi_name.lower()
                        
                        # Initialize KPI structure if needed
                        if normalized_kpi not in valid_kpis:
                            valid_kpis[normalized_kpi] = {}
                        
                        # Update the specific property
                        valid_kpis[normalized_kpi][property_name] = value
                        
                elif key == "identified_kpis":
                    # Special handling for KPI initialization
                    # Normalize all KPI names to lowercase and store original case mapping
                    normalized_kpis = []
                    kpi_case_map = {}
                    for kpi in value:
                        normalized = kpi.lower()
                        normalized_kpis.append(normalized)
                        kpi_case_map[normalized] = kpi
                    
                    # Store both normalized KPIs and their original case
                    task_data["identified_kpis"] = normalized_kpis
                    task_data["kpi_case_map"] = kpi_case_map
                    
                    # Initialize or maintain partial_results entries for each KPI
                    for kpi_name in normalized_kpis:
                        if kpi_name not in task_data["partial_results"]:
                            task_data["partial_results"][kpi_name] = {}
                        else:
                            # Preserve existing data for this KPI
                            valid_kpis[kpi_name] = task_data["partial_results"][kpi_name]
                            
                elif key == "current_kpi":
                    # Normalize current KPI name
                    task_data[key] = value.lower()
                else:
                    # Handle direct field updates
                    task_data[key] = value
            
            # Update partial_results with valid KPIs only
            for kpi, data in valid_kpis.items():
                # Only store KPIs that have actual data (visualization_url or insights)
                if data and (data.get('visualization_url') or data.get('insights')):
                    # Ensure both visualization_url and insights exist in the data
                    if 'visualization_url' not in data:
                        data['visualization_url'] = None
                    if 'insights' not in data:
                        data['insights'] = None
                    task_data["partial_results"][kpi] = data
            
            # Sort partial_results to maintain consistent order based on identified_kpis
            if "identified_kpis" in task_data:
                sorted_results = {}
                for kpi in task_data["identified_kpis"]:
                    if kpi in task_data["partial_results"]:
                        sorted_results[kpi] = task_data["partial_results"][kpi]
                task_data["partial_results"] = sorted_results
        
        # Debug: Print what we're about to save
        print(f"Saving to Redis - Task ID: {task_id}")
        print(f"Status: {status}, Progress: {progress}")
        if "partial_results" in task_data:
            print(f"Partial results keys: {list(task_data['partial_results'].keys())}")
            # Debug partial results content
            for kpi, data in task_data["partial_results"].items():
                print(f"KPI: {kpi}")
                print(f"Has visualization: {'visualization_url' in data}")
                print(f"Has insights: {'insights' in data}")
        
        # Serialize to JSON and save back to Redis
        json_data = json.dumps(task_data)
        redis_result = await redis_client.set(f"task:{task_id}", json_data)
        print(f"Redis set result: {redis_result}")
        
        return True
    except Exception as e:
        print(f"Error updating Redis task: {e}")
        # Log detailed error info including traceback
        import traceback
        traceback.print_exc()
        return False