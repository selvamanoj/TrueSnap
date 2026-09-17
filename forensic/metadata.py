from PIL import Image, ExifTags


# EXIF tag number -> readable name
EXIF_TAGS = {
    tag_id: name
    for tag_id, name in ExifTags.TAGS.items()
}


def safe_string(value):
    try:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace").strip()
        return str(value).strip()
    except Exception:
        return "Unreadable value"


def get_metadata(file_path):
    result = {
        "error": None,
        "has_exif": False,
        "datetime": {},
        "device": {},
        "software": {},
        "orientation": None,
        "color": {},
        "other": {},
        "indicators": []
    }

    try:
        with Image.open(file_path) as image:

            # Basic image information
            width, height = image.size

            exif = image.getexif()

            if not exif:
                result["indicators"].append(
                    "No EXIF metadata was detected. This is common for "
                    "screenshots, re-saved images, and some image formats. "
                    "It does not prove manipulation."
                )
                return result

            result["has_exif"] = True

            # Read every EXIF field
            raw_exif = {}

            for tag_id, value in exif.items():
                tag_name = EXIF_TAGS.get(tag_id, str(tag_id))
                raw_exif[tag_name] = safe_string(value)

            # Date and time information
            for tag in [
                "DateTime",
                "DateTimeOriginal",
                "DateTimeDigitized"
            ]:
                if tag in raw_exif:
                    result["datetime"][tag] = raw_exif[tag]

            # Camera/device information
            for tag in [
                "Make",
                "Model",
                "LensModel",
                "LensMake"
            ]:
                if tag in raw_exif:
                    result["device"][tag] = raw_exif[tag]

            # Software information
            for tag in [
                "Software",
                "ProcessingSoftware"
            ]:
                if tag in raw_exif:
                    result["software"][tag] = raw_exif[tag]

            # Orientation
            if "Orientation" in raw_exif:
                result["orientation"] = raw_exif["Orientation"]

            # Color information
            for tag in [
                "ColorSpace",
                "ExifImageWidth",
                "ExifImageHeight",
                "YCbCrPositioning"
            ]:
                if tag in raw_exif:
                    result["color"][tag] = raw_exif[tag]

            # Everything else
            used_tags = {
                "DateTime",
                "DateTimeOriginal",
                "DateTimeDigitized",
                "Make",
                "Model",
                "LensModel",
                "LensMake",
                "Software",
                "ProcessingSoftware",
                "Orientation",
                "ColorSpace",
                "ExifImageWidth",
                "ExifImageHeight",
                "YCbCrPositioning"
            }

            for key, value in raw_exif.items():
                if key not in used_tags:
                    result["other"][key] = value

            # ---------- Forensic indicators ----------

            software = (
                result["software"].get("Software")
                or result["software"].get("ProcessingSoftware")
            )

            if software:
                result["indicators"].append(
                    f"Software information detected: {software}. "
                    "This indicates that the file passed through this "
                    "software, but does not prove that the image was edited."
                )

            if result["device"]:
                result["indicators"].append(
                    "Camera or device information is present in the metadata."
                )
            else:
                result["indicators"].append(
                    "No camera/device information was found in the EXIF data."
                )

            if result["datetime"]:
                result["indicators"].append(
                    "Date/time metadata is available and may help establish "
                    "a rough processing timeline."
                )
            else:
                result["indicators"].append(
                    "No date/time metadata was found."
                )

            # Check EXIF dimensions against actual dimensions
            exif_width = raw_exif.get("ExifImageWidth")
            exif_height = raw_exif.get("ExifImageHeight")

            try:
                if exif_width and exif_height:
                    if (
                        int(exif_width) != width
                        or int(exif_height) != height
                    ):
                        result["indicators"].append(
                            f"EXIF dimensions ({exif_width}x{exif_height}) "
                            f"differ from actual dimensions "
                            f"({width}x{height}). The image may have been "
                            "resized or reprocessed."
                        )
            except (ValueError, TypeError):
                pass

            # GPS information
            if "GPSInfo" in raw_exif:
                result["indicators"].append(
                    "GPS location information appears to be present. "
                    "This may contain sensitive location information."
                )

    except FileNotFoundError:
        result["error"] = "File not found while reading metadata."

    except (OSError, SyntaxError):
        result["error"] = (
            "The file could not be parsed for metadata."
        )

    except Exception as e:
        result["error"] = f"Metadata analysis failed unexpectedly: {e}"

    return result