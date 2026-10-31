import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

if __name__ == "__main__":
    # Get environment
    app_env = os.getenv("APP_ENV", "development")
    
    # Configuration
    config = {
        "app": "app:app",
        "host": "0.0.0.0",
        "port": 8000,
        "reload": app_env == "development",
        "workers": 1 if app_env == "development" else 4,
        "log_level": "info",
    }
    
    print(f"Starting server in {app_env} mode...")
    print(f"API Docs: http://localhost:{config['port']}/docs")
    
    # Run the server
    uvicorn.run(**config)