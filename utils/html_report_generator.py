import os
import json
from datetime import datetime
import base64
import re
from typing import Dict, Any, List, Optional
import requests

def create_html_report(master_data_dict: Dict[str, Any], 
                      visualization_urls: Dict[str, str] = None,
                      output_filename: str = "data_analysis_report.html") -> str:
    """
    Generate a beautiful HTML report from KPI analysis data, business insights, and visualization URLs.
    
    Parameters:
    - master_data_dict: Dictionary with KPI data including raw_response and insights
    - visualization_urls: Dictionary with KPI names as keys and visualization URLs as values 
                         (optional, will use URLs from master_data_dict if not provided)
    - output_filename: Output HTML file name
    
    Returns:
    - Path to the generated HTML file
    """
    # Get current timestamp for the report
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Start building HTML content
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Deep Analysis Report</title>
        <style>
            :root {{
                --primary-color: #1a73e8;
                --secondary-color: #f5f7fa;
                --accent-color: #4285f4;
                --text-color: #202124;
                --light-text: #5f6368;
                --border-color: #dadce0;
                --success-color: #0f9d58;
                --info-color: #137cbd;
                --warning-color: #f9a825;
                --box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            }}
            
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                color: var(--text-color);
                background-color: #f8f9fa;
                padding-bottom: 40px;
            }}
            
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 20px;
            }}
            
            header {{
                background: linear-gradient(135deg, var(--primary-color), var(--accent-color));
                color: white;
                padding: 40px 0;
                margin-bottom: 40px;
            }}
            
            header .container {{
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
            }}
            
            header h1 {{
                font-size: 2.5rem;
                margin-bottom: 10px;
                font-weight: 300;
                letter-spacing: 0.5px;
            }}
            
            header p {{
                font-size: 1.1rem;
                opacity: 0.9;
            }}
            
            .summary-section {{
                background-color: white;
                border-radius: 8px;
                padding: 25px;
                margin-bottom: 40px;
                box-shadow: var(--box-shadow);
            }}
            
            .summary-section h2 {{
                color: var(--primary-color);
                font-size: 1.8rem;
                margin-bottom: 20px;
                font-weight: 400;
                border-bottom: 2px solid var(--border-color);
                padding-bottom: 10px;
            }}
            
            .kpi-list {{
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-top: 15px;
            }}
            
            .kpi-tag {{
                background-color: var(--secondary-color);
                border-radius: 20px;
                padding: 8px 16px;
                font-size: 0.9rem;
                color: var(--primary-color);
                border: 1px solid var(--border-color);
            }}
            
            .kpi-cards {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
                margin-top: 20px;
            }}
            
            .kpi-card {{
                background-color: rgba(var(--primary-color-rgb), 0.05);
                border-radius: 8px;
                padding: 20px;
                transition: transform 0.3s ease;
                cursor: pointer;
                border-left: 4px solid var(--primary-color);
            }}
            
            .kpi-card:hover {{
                transform: translateY(-5px);
            }}
            
            .kpi-card h3 {{
                color: var(--primary-color);
                margin-bottom: 10px;
                font-weight: 500;
            }}
            
            .kpi-section {{
                background-color: white;
                border-radius: 8px;
                margin-bottom: 40px;
                overflow: hidden;
                box-shadow: var(--box-shadow);
            }}
            
            .kpi-header {{
                background: linear-gradient(to right, var(--primary-color), var(--accent-color));
                color: white;
                padding: 20px 25px;
                position: relative;
            }}
            
            .kpi-header h2 {{
                font-size: 1.8rem;
                font-weight: 400;
            }}
            
            .kpi-content {{
                padding: 25px;
            }}
            
            .visualization {{
                text-align: center;
                margin: 20px 0 30px;
                padding: 10px;
                background-color: var(--secondary-color);
                border-radius: 8px;
            }}
            
            .visualization img {{
                max-width: 100%;
                height: auto;
                border-radius: 4px;
                box-shadow: var(--box-shadow);
            }}
            
            .analysis-container, .insights-container {{
                margin-bottom: 30px;
            }}
            
            .analysis-container h3, .insights-container h3 {{
                font-size: 1.4rem;
                color: var(--primary-color);
                margin-bottom: 15px;
                font-weight: 500;
                border-bottom: 1px solid var(--border-color);
                padding-bottom: 10px;
            }}
            
            .analysis-content {{
                background-color: var(--secondary-color);
                padding: 20px;
                border-radius: 8px;
                font-family: 'Courier New', Courier, monospace;
                white-space: pre-wrap;
                overflow-x: auto;
                border-left: 4px solid var(--info-color);
            }}
            
            .insights-content {{
                background-color: rgba(15, 157, 88, 0.1);
                padding: 20px;
                border-radius: 8px;
                line-height: 1.7;
                border-left: 4px solid var(--success-color);
            }}
            
            .insights-content p {{
                margin-bottom: 15px;
            }}
            
            .back-to-top {{
                background-color: var(--primary-color);
                color: white;
                border: none;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                position: fixed;
                bottom: 30px;
                right: 30px;
                cursor: pointer;
                box-shadow: 0 4px 10px rgba(0, 0, 0, 0.2);
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5rem;
                transition: background-color 0.3s;
            }}
            
            .back-to-top:hover {{
                background-color: var(--accent-color);
            }}
            
            footer {{
                margin-top: 40px;
                text-align: center;
                color: var(--light-text);
                font-size: 0.9rem;
            }}
            
            /* Navigation */
            .navbar {{
                position: sticky;
                top: 0;
                background-color: white;
                box-shadow: var(--box-shadow);
                z-index: 100;
                margin-bottom: 40px;
            }}
            
            .nav-container {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 15px 20px;
            }}
            
            .logo {{
                font-size: 1.4rem;
                font-weight: 600;
                color: var(--primary-color);
            }}
            
            .nav-links {{
                display: flex;
                gap: 20px;
            }}
            
            .nav-link {{
                color: var(--text-color);
                text-decoration: none;
                padding: 8px 12px;
                border-radius: 4px;
                transition: background-color 0.3s;
            }}
            
            .nav-link:hover {{
                background-color: var(--secondary-color);
                color: var(--primary-color);
            }}
            
            /* Responsive styles */
            @media (max-width: 768px) {{
                .kpi-header h2 {{
                    font-size: 1.5rem;
                }}
                
                .kpi-content {{
                    padding: 15px;
                }}
                
                header h1 {{
                    font-size: 2rem;
                }}
            }}
            
            /* Custom scrollbar */
            ::-webkit-scrollbar {{
                width: 8px;
                height: 8px;
            }}
            
            ::-webkit-scrollbar-track {{
                background: #f1f1f1;
            }}
            
            ::-webkit-scrollbar-thumb {{
                background: var(--primary-color);
                border-radius: 4px;
            }}
            
            ::-webkit-scrollbar-thumb:hover {{
                background: var(--accent-color);
            }}
            
            /* Animation */
            @keyframes fadeIn {{
                from {{ opacity: 0; transform: translateY(20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            
            .kpi-section {{
                animation: fadeIn 0.5s ease-out forwards;
            }}
            
            .kpi-section:nth-child(1) {{ animation-delay: 0.1s; }}
            .kpi-section:nth-child(2) {{ animation-delay: 0.2s; }}
            .kpi-section:nth-child(3) {{ animation-delay: 0.3s; }}
            .kpi-section:nth-child(4) {{ animation-delay: 0.4s; }}
            .kpi-section:nth-child(5) {{ animation-delay: 0.5s; }}
        </style>
    </head>
    <body>
        <!-- Back to top button -->
        <button class="back-to-top" onclick="window.scrollTo({{top: 0, behavior: 'smooth'}})">↑</button>
        
        <!-- Header -->
        <header>
            <div class="container">
                <h1>Deep Analysis Report</h1>
                <p>Generated on {timestamp}</p>
            </div>
        </header>
        
        <!-- Navigation -->
        <nav class="navbar">
            <div class="container nav-container">
                <div class="logo">Deep Analysis</div>
                <div class="nav-links">
                    <a href="#summary" class="nav-link">Summary</a>
                    <a href="#kpis" class="nav-link">KPIs</a>
                </div>
            </div>
        </nav>
        
        <!-- Summary Section -->
        <section id="summary" class="container">
            <div class="summary-section">
                <h2>Executive Summary</h2>
                <p>This report presents a comprehensive deep analysis of {len(master_data_dict) - 1 if "summary" in master_data_dict else len(master_data_dict)} key performance indicators derived from the dataset. Each KPI is analyzed with detailed metrics, visualizations, and business insights to support data-driven decision making.</p>
                
                {f'<div class="executive-insights-container"><h3 style="margin-top: 20px; color: var(--primary-color);">AI-Generated Summary</h3><div class="executive-insights-content">{master_data_dict.get("summary", "")}</div></div>' if "summary" in master_data_dict else ""}
                
                <h3 style="margin-top: 20px; color: var(--primary-color);">Analyzed KPIs</h3>
                <div class="kpi-list">
    """
    
    # Add KPI tags
    for kpi_name in master_data_dict.keys():
        html_content += f'<span class="kpi-tag">{kpi_name}</span>\n'
    
    html_content += """
                </div>
                
                <h3 style="margin-top: 25px; color: var(--primary-color);">Quick Navigation</h3>
                <div class="kpi-cards">
    """
    
    # Add quick navigation cards
    for kpi_name in master_data_dict.keys():
        # Create a valid ID from KPI name
        kpi_id = re.sub(r'[^a-zA-Z0-9_-]', '_', kpi_name)
        html_content += f"""
                    <div class="kpi-card" onclick="document.getElementById('{kpi_id}').scrollIntoView({{behavior: 'smooth'}})">
                        <h3>{kpi_name}</h3>
                        <p>View analysis and insights</p>
                    </div>
        """
    
    html_content += """
                </div>
            </div>
        </section>
        
        <!-- KPIs Section -->
        <section id="kpis" class="container">
    """
    
    # Add each KPI section
    for kpi_name, kpi_data in master_data_dict.items():
        # Skip the summary key as it's handled separately
        if kpi_name == "summary":
            continue
            
        # Create a valid ID from KPI name
        kpi_id = re.sub(r'[^a-zA-Z0-9_-]', '_', kpi_name)
        
        # Get visualization URL
        visualization_url = ""
        if visualization_urls and kpi_name in visualization_urls:
            visualization_url = visualization_urls[kpi_name]
        elif "visualization" in kpi_data and "visualization_url" in kpi_data["visualization"]:
            visualization_url = kpi_data["visualization"]["visualization_url"]
        
        # Get raw analysis and insights
        raw_analysis = kpi_data.get("raw_response", "No analysis available")
        insights = kpi_data.get("insights", "No insights available")
        
        html_content += f"""
            <div id="{kpi_id}" class="kpi-section">
                <div class="kpi-header">
                    <h2>{kpi_name}</h2>
                </div>
                <div class="kpi-content">
                    <!-- Visualization -->
                    <div class="visualization">
        """
        
        if visualization_url:
            html_content += f'<img src="{visualization_url}" alt="Visualization for {kpi_name}">'
        else:
            html_content += '<p style="padding: 40px; color: var(--light-text);">No visualization available</p>'
        
        html_content += f"""
                    </div>
                    
                    <!-- Analysis Results -->
                    <div class="analysis-container">
                        <h3>Analysis Results</h3>
                        <div class="analysis-content">
{raw_analysis}
                        </div>
                    </div>
                    
                    <!-- Business Insights -->
                    <div class="insights-container">
                        <h3>Business Insights</h3>
                        <div class="insights-content">
                            {insights}
                        </div>
                    </div>
                </div>
            </div>
        """
    
    # Close the HTML structure
    html_content += """
        </section>
        
        <!-- Footer -->
        <footer class="container">
            <p>© 2025 Deep Analysis. All rights reserved.</p>
            <p style="margin-top: 10px;">Generated with ❤️ by Deep Analysis</p>
        </footer>
        
        <script>
            // JavaScript for interactive elements
            document.addEventListener('DOMContentLoaded', function() {
                // Show/hide back to top button based on scroll position
                window.addEventListener('scroll', function() {
                    const backToTopButton = document.querySelector('.back-to-top');
                    if (window.scrollY > 300) {
                        backToTopButton.style.display = 'flex';
                    } else {
                        backToTopButton.style.display = 'none';
                    }
                });
                
                // Initially hide the button
                document.querySelector('.back-to-top').style.display = 'none';
            });
        </script>
    </body>
    </html>
    """
    
    # # Write the HTML file
    # with open(output_filename, 'w', encoding='utf-8') as f:
    #     f.write(html_content)
    
    # print(f"HTML report created successfully: {output_filename}")
    return html_content


def generate_html_report(json_path="master_data_dictionary.json", output_filename="data_analysis_report.html"):
    """
    Generate an HTML report from the master data dictionary JSON file.
    
    Parameters:
    - json_path: Path to the master data dictionary JSON file
    - output_filename: Output HTML file name
    
    Returns:
    - Path to the generated HTML file
    """
    # Load the master data dictionary
    try:
        with open(json_path, 'r') as f:
            master_data_dict = json.load(f)
    except Exception as e:
        print(f"Error loading master data dictionary: {e}")
        return None
    
    # Generate the HTML report
    return create_html_report(master_data_dict, output_filename=output_filename)


def download_local_images_as_base64(master_data_dict):
    """
    Download images from URLs in master_data_dict and replace with base64 encoded images.
    This makes the HTML report self-contained.
    
    Parameters:
    - master_data_dict: Dictionary with KPI data including visualization URLs
    
    Returns:
    - Updated master_data_dict with base64 encoded images
    """
    updated_dict = master_data_dict.copy()
    
    for kpi_name, kpi_data in updated_dict.items():
        if "visualization" in kpi_data and "visualization_url" in kpi_data["visualization"]:
            url = kpi_data["visualization"]["visualization_url"]
            try:
                # Download the image
                response = requests.get(url)
                if response.status_code == 200:
                    # Convert to base64
                    image_data = base64.b64encode(response.content).decode('utf-8')
                    # Determine the image type
                    content_type = response.headers.get('Content-Type', 'image/png')
                    # Replace the URL with base64 data
                    updated_dict[kpi_name]["visualization"]["visualization_url"] = f"data:{content_type};base64,{image_data}"
            except Exception as e:
                print(f"Error downloading image for {kpi_name}: {e}")
    
    return updated_dict


# Usage example
if __name__ == "__main__":
    # Option 1: Generate from JSON file
    report_path = generate_html_report()
    print(f"Report generated at: {report_path}")
    
    # Option 2: Load JSON, create self-contained report with embedded images
    try:
        with open("master_data_dictionary.json", 'r') as f:
            data_dict = json.load(f)
        
        # Embed images as base64 (optional)
        # data_dict_with_embedded_images = download_local_images_as_base64(data_dict)
        # report_path = create_html_report(data_dict_with_embedded_images, output_filename="self_contained_report.html")
        
        report_path = create_html_report(data_dict, output_filename="data_analysis_report.html")
        print(f"Self-contained report generated at: {report_path}")
    except Exception as e:
        print(f"Error creating self-contained report: {e}")