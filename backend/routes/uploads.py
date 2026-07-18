import os
import tempfile

from flask import jsonify, request, session
from google.cloud import vision

from backend.clients import get_gemini_model, get_vision_client


PDF_MAX_BYTES = 10 * 1024 * 1024
IMAGE_MAX_BYTES = 8 * 1024 * 1024


def _validate_file(file, *, extensions, mime_types, max_bytes, signatures):
    filename = (file.filename or "").strip()
    extension = os.path.splitext(filename)[1].lower()
    if extension not in extensions:
        return f"Allowed file types: {', '.join(sorted(extensions))}."
    if file.mimetype not in mime_types:
        return "The uploaded file content type is invalid."

    header = file.stream.read(16)
    file.stream.seek(0)
    if not any(header.startswith(signature) for signature in signatures):
        return "The uploaded file content does not match its extension."

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size <= 0:
        return "The uploaded file is empty."
    if size > max_bytes:
        return f"The uploaded file is too large. Maximum size is {max_bytes // (1024 * 1024)} MB."
    return None


def _pdf_to_markdown(pdf_path):
    try:
        import pymupdf4llm
    except ImportError as exc:
        raise RuntimeError(
            "PDF parsing is unavailable because PyMuPDF failed to load. "
            "Try reinstalling PyMuPDF/pymupdf4llm or use Python 3.12/3.13."
        ) from exc

    return pymupdf4llm.to_markdown(pdf_path)


def register_routes(app):
    @app.route("/upload", methods=["POST"])
    def upload():
        if "user_id" not in session:
            return jsonify({"error": "User not logged in."}), 401
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded!"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file!"}), 400

        validation_error = _validate_file(
            file,
            extensions={".pdf"},
            mime_types={"application/pdf"},
            max_bytes=PDF_MAX_BYTES,
            signatures=(b"%PDF-",),
        )
        if validation_error:
            return jsonify({"error": validation_error}), 400

        temp_path = None
        markdown_output_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_pdf:
                file.save(temp_pdf.name)
                temp_path = temp_pdf.name

            md_text = _pdf_to_markdown(temp_path)
            if not md_text or not md_text.strip():
                return jsonify({"error": "No readable text found in PDF."}), 400
            if len(md_text) > 1_000_000:
                return jsonify({"error": "The extracted PDF text is too large to process."}), 400

            with tempfile.NamedTemporaryFile(delete=False, suffix=".md") as temp_md:
                temp_md.write(md_text.encode())
                markdown_output_path = temp_md.name

            query = f"{md_text}\nIdentify the topic and subtopic for above text clearly, give response as just the one 'topic name: subtopic name' in the response."
            response = get_gemini_model().generate_content(query)
            topic = response.text.strip()

            return jsonify({"topic": topic})
        except Exception as exc:
            print(f"Error: {str(exc)}")
            return jsonify({"error": str(exc)}), 500
        finally:
            for path in [temp_path, markdown_output_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                    except Exception:
                        pass

    @app.route("/upload-image", methods=["POST"])
    def upload_image():
        if "user_id" not in session:
            return jsonify({"error": "User not logged in."}), 401
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded!"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No selected file!"}), 400

        validation_error = _validate_file(
            file,
            extensions={".jpg", ".jpeg", ".png"},
            mime_types={"image/jpeg", "image/png"},
            max_bytes=IMAGE_MAX_BYTES,
            signatures=(b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n"),
        )
        if validation_error:
            return jsonify({"error": validation_error}), 400

        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_img:
                file.save(temp_img.name)
                temp_path = temp_img.name

            with open(temp_path, "rb") as image_file:
                image_content = image_file.read()

            image = vision.Image(content=image_content)
            response = get_vision_client().text_detection(image=image)
            texts = response.text_annotations

            if not texts:
                return jsonify({"error": "No text found in image!"}), 400

            extracted_text = texts[0].description.strip()
            if len(extracted_text) > 100_000:
                return jsonify({"error": "The extracted image text is too large to process."}), 400
            query = f"{extracted_text}\nIdentify the topic and subtopic for the above text clearly, give response as just the 'topic name: subtopic name' in the response."
            response = get_gemini_model().generate_content(query)
            topic = response.text.strip()

            return jsonify({"topic": topic})
        except Exception as exc:
            print(f"Error: {str(exc)}")
            return jsonify({"error": str(exc)}), 500
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
