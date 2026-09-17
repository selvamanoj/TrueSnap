import os
from PIL import Image


SUPPORTED_EXTENSIONS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp"
)


def format_file_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.2f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / (1024 ** 2):.2f} MB"
    else:
        return f"{size_bytes / (1024 ** 3):.2f} GB"


def is_supported_image(file_path):
    return file_path.lower().endswith(SUPPORTED_EXTENSIONS)


def get_basic_file_info(file_path):
    info = {
        "file_name": "",
        "file_extension": "",
        "file_size": "",
        "image_format": "",
        "width": "",
        "height": "",
        "color_mode": "",
        "aspect_ratio": "",
        "error": None
    }

    try:
        file_name = os.path.basename(file_path)
        _, ext = os.path.splitext(file_name)
        size_bytes = os.path.getsize(file_path)

        info["file_name"] = file_name
        info["file_extension"] = ext.upper().replace(".", "")
        info["file_size"] = format_file_size(size_bytes)

        with Image.open(file_path) as img:
            width, height = img.size

            info["image_format"] = img.format or "UNKNOWN"
            info["width"] = f"{width} px"
            info["height"] = f"{height} px"
            info["color_mode"] = img.mode

            if height != 0:
                info["aspect_ratio"] = f"{width / height:.3f} : 1"
            else:
                info["aspect_ratio"] = "N/A"

    except FileNotFoundError:
        info["error"] = "File not found."

    except Exception as e:
        info["error"] = f"Unable to read image: {e}"

    return info