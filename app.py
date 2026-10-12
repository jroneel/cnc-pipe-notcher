import io
import hashlib
from pathlib import Path
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from cam import CAMError, load_mesh, plan, gcode, viewer_gcode
from werkzeug.exceptions import HTTPException
from stock import detect_stock

class CAMApp(Flask):
    def send_static_file(self, filename):
        if filename.endswith('.mjs'):
            # Windows registry mappings can label .mjs as binary data. Browsers
            # reject such modules. Always send fresh, explicitly typed JavaScript.
            response = send_from_directory(self.static_folder, filename,
                                           mimetype='text/javascript', conditional=False)
            response.headers['Cache-Control'] = 'no-store'
            return response
        return super().send_static_file(filename)


app = CAMApp(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.context_processor
def asset_versions():
    def static_version(filename):
        contents = (Path(app.static_folder) / filename).read_bytes()
        return hashlib.sha256(b'javascript-delivery-v2:' + contents).hexdigest()[:16]
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
            export_format = request.form.get('export_format', 'machine')
            if export_format not in ('machine', 'viewer'):
                raise CAMError('Unknown G-code export format')
            program = viewer_gcode(result) if export_format == 'viewer' else gcode(result, request.form)
            filename = 'notcher-viewer-only.nc' if export_format == 'viewer' else 'notcher.nc'
            return Response(program, mimetype="text/plain",
                            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
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
