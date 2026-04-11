import os
from controllers.pipeline import process_manga_page


if __name__ == "__main__":
    input_image = "raw/spanish_comic.png"
    
    if os.path.exists(input_image):
        process_manga_page(input_image)
    else:
        print(f"Error: {input_image} not found. Please add an image to the folder.")