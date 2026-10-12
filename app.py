import io
import hashlib
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response
from cam import CAMError, load_mesh, plan, gcode
from werkzeug.exceptions import HTTPException
from stock import detect_stock

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.context_processor
def asset_versions():
    def static_version(filename):
        return hashlib.sha256((Path(app.static_folder) / filename).read_bytes()).hexdigest()[:16]
    return {"static_version": static_version}


@app.get("/")
def index():
    return Response(render_template("index.html"), headers={"Cache-Control": "no-store"})


@app.post("/api/detect")
@app.post("/api/plan")
def create_plan():
    upload = request.files.get("model")
    if not upload:
        return jsonify(error="Choose an STL or OBJ file"), 400
    try:
        extension = upload.filename.rsplit(".", 1)[-1].lower()
        mesh = load_mesh(io.BytesIO(upload.read()), extension)
        if request.path == "/api/detect":
            return jsonify(detect_stock(mesh))
        settings = request.form.to_dict()
        detected = None
        if settings.get('stock_mode', 'auto') == 'auto':
            detected = detect_stock(mesh)
            settings.update(detected)
        elif settings.get('stock_mode') != 'manual':
            raise CAMError("Unknown stock detection mode")
        result = plan(mesh, settings)
        result['detected_stock'] = detected
        if request.form.get("export") == "yes":
            return Response(gcode(result, request.form), mimetype="text/plain",
                            headers={"Content-Disposition": 'attachment; filename="notcher.nc"'})
        return jsonify(result)
    except (CAMError, ValueError, IndexError, TypeError) as exc:
        return jsonify(error=str(exc)), 400


@app.errorhandler(413)
def too_large(_):
    return jsonify(error="File exceeds 20 MB"), 413


@app.errorhandler(HTTPException)
def http_error(exc):
    if request.path.startswith("/api/"):
        return jsonify(error=exc.description), exc.code
    return exc


@app.errorhandler(Exception)
def unexpected_error(exc):
    app.logger.exception("Unhandled request failure")
    if request.path.startswith("/api/"):
        return jsonify(error="Could not process the model. Check the application server logs for details."), 500
    return "Application error. Check server logs.", 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
