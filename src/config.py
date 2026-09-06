import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

# We can store any other configuration here later.
# For now, we will just use it to prepare the output directories.

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")

def get_video_dir(video_id: str) -> str:
    """Gets the output directory for a specific video."""
    video_dir = os.path.join(OUTPUT_DIR, video_id)
    os.makedirs(video_dir, exist_ok=True)
    return video_dir

def get_image_dir(video_id: str) -> str:
    """Gets the image output directory for a specific video."""
    video_dir = get_video_dir(video_id)
    image_dir = os.path.join(video_dir, "images")
    os.makedirs(image_dir, exist_ok=True)
    return image_dir
