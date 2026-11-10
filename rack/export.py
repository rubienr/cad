#!/usr/bin/env python3
"""Export independent FreeCAD variants described by a Python-literal config.

Usage (absolute paths make invocation independent of the working directory):
    python3 /path/to/export.py /project/export-config.py
    python3 /path/to/export.py /project/export-config.py --export
    python3 /path/to/export.py /project/export-config.py --screenshot
    python3 /path/to/export.py /project/export-config.py -e -s
    python3 /path/to/export.py /project/export-config.py -e -s -p 4
    Config only: list permutations and planned model filenames, without writes
    or loading FreeCAD. No arguments: show help. Model format comes from the
    configured file_extension (e.g. "stl" or "step").

Python dependencies:
    GNU Parallel (the parallel executable) is required for export/screenshot
    modes. Worker limit: -p/--parallel, then exported PARALLEL, then 4.
    Python 3.10+ and the FreeCAD Python modules FreeCAD and Part, supplied by
    a FreeCAD installation (1.0+ for App::VarSet). No pip packages are needed.
    Use a Python interpreter ABI-compatible with that FreeCAD installation.
    Common Linux module directories are detected automatically. Otherwise put
    the directory containing FreeCAD.so / FreeCAD.pyd on PYTHONPATH and ensure
    its shared libraries are available. A GUI/display is not required.
    Screenshot-only mode additionally needs FreeCADGui, matching PySide6, and
    an X11/XWayland display on Linux. It uses software OpenGL, a temporary
    profile and its own embedded GUI process, never an existing FreeCAD session.
    A separate window appears briefly. PNGs use an isometric view; image folder,
    dimensions and background are configured in screenshots (see below).
    --export/-e writes CAD files; --screenshot/-s writes PNGs. Both flags run
    both outputs from the same recomputed shape in one worker per variant.
    All jobs are attempted even if some fail. Both outputs are staged before
    publication; failed variants leave any outputs from earlier runs untouched.

Configuration consists of assignments (comments are allowed):
    source_filename, file_extension, file_prefix, output_directory, exports.
    Optional screenshots dictionary: output_directory (default "images"),
    width (1600), height (1200), background ("#404040"), screenshot (True).
    screenshots.screenshot sets the default group enablement in --screenshot
    mode; groups may override it. CAD mode ignores screenshot enablement.
    Background accepts
    an RGB hex color (#RRGGBB) or "Transparent". Dimensions are pixel integers.
    exports accepts a group dictionary or a nonempty list of independent group
    dictionaries. Each list item has its own matrix and groups; items do not
    inherit from or cross with one another. Filename collisions are checked
    across the whole list. Each group dictionary has values, matrix, groups, name, objects and
    optional screenshot (boolean, defaults to screenshots.screenshot). screenshot=False suppresses
    that group's PNGs only. Nested groups inherit it and may override it.
    values maps visible VarSet labels to variable/value dictionaries.
    matrix.values uses the same structure with nonempty candidate lists.
    Nested groups inherit definitions, name and objects. Inner definitions
    replace outer values or axes before expansion. A variable cannot appear in
    both values and matrix.values at the same level. Only leaf groups export,
    expanding the cross product across every VarSet. Leaves need name/objects.
    Relative source/output paths are relative to the configuration directory.
    Values support Python literals, references to previously assigned settings,
    and string concatenation with + (also inside dictionaries/lists).
    The config is parsed, not executed. Imports, calls and attribute access
    are not allowed.

Units: strings such as "1 mm" are assigned using FreeCAD's unit handling;
numeric values use FreeCAD's internal property units (e.g. mm for lengths).
Overrides replace any expression on the overridden property only.
Unspecified properties always come from a freshly opened original document.

Filenames are prefix + expanded name + automatic matrix suffix + extension.
The suffix includes effective matrix axes sorted by VarSet label and variable
name: -name-value_name-value. Fixed values are excluded; an inner fixed value
removes an inherited axis from the suffix. Duplicate axis names across VarSets
are qualified with their VarSet label. No axes means no suffix.
Templates accept {object}
and {VarSet label.variable_name} for effective configured values. Literal
braces use {{ and }}; format specs/conversions are unsupported. Unsafe filename
characters become underscores ("1 mm" -> "1_mm"). Collisions are errors.
Supported formats: STEP/STP, IGES/IGS, BREP/BRP, STL, using explicit exporters.
STL uses FreeCAD's default tessellation; CAD formats preserve exact geometry.
Each variant is staged and published before processing the next. Failed variants
are reported and processing continues; successful outputs are retained. Any
variant failure produces a final summary and nonzero exit status. Configuration
errors and colliding names are rejected before processing. Existing output
files are replaced by default; --no-overwrite rejects them before processing.
Documents are never saved.
"""

import argparse
import ast
import copy
from contextlib import ExitStack, contextmanager, nullcontext
import importlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import sys
import string
import subprocess
import shutil
import shlex
import tempfile
import xml.etree.ElementTree as ET
import zipfile


EXPORTERS = {
    "step": "exportStep", "stp": "exportStep",
    "iges": "exportIges", "igs": "exportIges",
    "brep": "exportBrep", "brp": "exportBrep", "stl": "exportStl",
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def component(value):
    text = re.sub(r"[^\w.\-]", "_", str(value), flags=re.UNICODE).strip(". ")
    require(bool(text), f"Empty filename component after sanitizing {value!r}")
    if re.fullmatch(r"(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", text):
        text = "_" + text
    return text


def filename(prefix, template, label, values, extension, matrix_keys=()):
    fields = {"object": label}
    for (varset, variable), value in values.items():
        key = f"{varset}.{variable}"
        require(key not in fields, f"Ambiguous template field: {key}")
        fields[key] = value
    parts = []
    for literal, field, spec, conversion in string.Formatter().parse(template):
        parts.append(literal)
        if field is not None:
            require(not spec and conversion is None, "Name templates do not support format specs or conversions")
            require(field in fields, f"Unknown name template field: {field!r}")
            parts.append(str(fields[field]))
    axes = sorted(matrix_keys)
    suffix = []
    for varset, variable in axes:
        repeated = sum(name == variable for _, name in axes) > 1
        name = f"{varset}.{variable}" if repeated else variable
        suffix.append(f"{component(name)}-{component(values[varset, variable])}")
    return component(prefix + "".join(parts)) + (
        "-" + "_".join(suffix) if suffix else "") + "." + extension


def definitions(mapping, matrix, context):
    require(isinstance(mapping, dict), f"{context}: expected a dictionary")
    result = {}
    for varset, variables in mapping.items():
        require(isinstance(varset, str) and varset, f"{context}: invalid VarSet label")
        require(isinstance(variables, dict), f"{context}: {varset!r} must map variables to values")
        for name, value in variables.items():
            require(isinstance(name, str) and name, f"{context}: invalid variable name")
            require(matrix or not isinstance(value, (list, tuple)),
                    f"{context}: {varset}.{name} expects a single fixed value, got {value!r}; "
                    "use matrix.values for a list of candidate values, or remove the brackets for a fixed value")
            candidates = value if matrix else [value]
            require(isinstance(candidates, list) and candidates,
                    f"{context}: {varset}.{name} requires a nonempty candidate list")
            for candidate in candidates:
                require(type(candidate) in (str, int, float, bool),
                        f"{context}: unsupported value for {varset}.{name}")
                require(not isinstance(candidate, float) or math.isfinite(candidate),
                        f"{context}: nonfinite value for {varset}.{name}")
            result[varset, name] = candidates
    return result


def expand_groups(group, inherited=None, name=None, objects=None, context="exports",
                  inherited_axes=(), screenshot=True):
    require(isinstance(group, dict), f"{context}: group must be a dictionary")
    require(not set(group) - {"values", "matrix", "groups", "name", "objects", "screenshot"},
            f"{context}: unknown group keys")
    screenshot = group.get("screenshot", screenshot)
    require(type(screenshot) is bool, f"{context}: screenshot must be True or False")
    fixed = definitions(group.get("values", {}), False, context + ".values")
    matrix = group.get("matrix", {})
    require(isinstance(matrix, dict) and not set(matrix) - {"values"},
            f"{context}: matrix must contain only values")
    axes = definitions(matrix.get("values", {}), True, context + ".matrix.values")
    require(not fixed.keys() & axes.keys(),
            f"{context}: variables occur in both values and matrix.values: {fixed.keys() & axes.keys()}")
    effective = dict(inherited or {})
    effective.update(fixed)
    effective.update(axes)
    effective_axes = (set(inherited_axes) - fixed.keys()) | axes.keys()
    if "name" in group:
        name = group["name"]
        require(isinstance(name, str) and name, f"{context}: name must be a nonempty string")
    if "objects" in group:
        objects = group["objects"]
        require(isinstance(objects, list) and objects
                and all(isinstance(label, str) and label for label in objects),
                f"{context}: objects must be a nonempty list of labels")
    if "groups" in group:
        children = group["groups"]
        require(isinstance(children, list) and children, f"{context}: groups must be a nonempty list")
        for index, child in enumerate(children, 1):
            yield from expand_groups(child, effective, name, objects, f"{context}.groups[{index}]",
                                     effective_axes, screenshot)
    else:
        require(name is not None and objects is not None, f"{context}: leaf requires name and objects")
        keys = sorted(effective)
        for combination in itertools.product(*(effective[key] for key in keys)):
            yield {"context": context, "name": name, "objects": objects,
                   "screenshot": screenshot,
                   "matrix_keys": sorted(effective_axes),
                   "values": dict(zip(keys, combination))}


def expand_exports(exports, screenshot=True):
    if isinstance(exports, dict):
        yield from expand_groups(exports, screenshot=screenshot)
        return
    require(isinstance(exports, list) and exports,
            "exports must be a group dictionary or a nonempty list of group dictionaries")
    for index, block in enumerate(exports, 1):
        yield from expand_groups(block, context=f"exports[{index}]", screenshot=screenshot)


def config_value(node, settings):
    """Evaluate the small config expression language without executing Python."""
    if isinstance(node, ast.Name):
        require(node.id in settings,
                f"Line {node.lineno}: unknown or forward reference {node.id!r}")
        return copy.deepcopy(settings[node.id])
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = config_value(node.left, settings)
        right = config_value(node.right, settings)
        require(isinstance(left, str) and isinstance(right, str),
                f"Line {node.lineno}: + supports string concatenation only")
        return left + right
    if isinstance(node, (ast.List, ast.Tuple)):
        values = [config_value(item, settings) for item in node.elts]
        return tuple(values) if isinstance(node, ast.Tuple) else values
    if isinstance(node, ast.Dict):
        require(all(key is not None for key in node.keys),
                f"Line {node.lineno}: dictionary unpacking is not supported")
        return {config_value(key, settings): config_value(value, settings)
                for key, value in zip(node.keys, node.values)}
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError) as error:
        raise ValueError(f"Line {node.lineno}: unsupported config expression; use literals, "
                         "earlier setting names, or string concatenation with +") from error


def read_config(path, screenshot=False, overwrite=True):
    config = {}
    for node in ast.parse(path.read_text(encoding="utf-8"), filename=str(path)).body:
        require(isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name),
                "Config must contain only single-name assignments")
        key = node.targets[0].id
        require(key not in config, f"Duplicate config key: {key}")
        config[key] = config_value(node.value, config)
    keys = {"source_filename", "file_extension", "file_prefix", "output_directory", "exports"}
    require(keys <= set(config) and not set(config) - keys - {"screenshots"},
            f"Config requires {sorted(keys)}; optional key: screenshots")
    for key in keys - {"exports"}:
        require(isinstance(config[key], str), f"{key} must be a string")
    require(bool(config["source_filename"]), "source_filename must not be empty")
    require(bool(config["output_directory"]), "output_directory must not be empty")
    images = config.get("screenshots", {})
    defaults = {"output_directory": "images", "width": 1600,
                "height": 1200, "background": "#404040", "screenshot": True}
    require(isinstance(images, dict) and not set(images) - set(defaults),
            f"screenshots must be a dictionary with keys from {sorted(defaults)}")
    images = defaults | images
    require(type(images["screenshot"]) is bool,
            "screenshots.screenshot must be True or False")
    require(isinstance(images["output_directory"], str) and images["output_directory"],
            "screenshots.output_directory must be a nonempty string")
    for key in ("width", "height"):
        require(type(images[key]) is int and 1 <= images[key] <= 16384,
                f"screenshots.{key} must be an integer from 1 to 16384")
    background = images["background"]
    require(isinstance(background, str) and
            (background == "Transparent" or re.fullmatch(r"#[0-9a-fA-F]{6}", background)),
            'screenshots.background must be #RRGGBB or "Transparent"')
    config["screenshots"] = images
    extension = config["file_extension"].lower().lstrip(".")
    require(extension in EXPORTERS, f"Unsupported format {extension!r}; choose {sorted(EXPORTERS)}")
    config["file_extension"] = extension
    source = (path.parent / config["source_filename"]).resolve()
    output = (path.parent / (images["output_directory"] if screenshot
                             else config["output_directory"])).resolve()
    require(source.is_file() and source.suffix.lower() == ".fcstd",
            f"Source must be an existing FCStd file: {source}")
    variants = list(expand_exports(config["exports"], screenshot=images["screenshot"]))
    config["skipped_screenshots"] = sum(not v["screenshot"] for v in variants) if screenshot else 0
    if screenshot:
        variants = [v for v in variants if v["screenshot"]]
    planned = set()
    for variant in variants:
        variant["filenames"] = []
        for label in variant["objects"]:
            name = filename(config["file_prefix"], variant["name"], label, variant["values"],
                            "png" if screenshot else extension, variant["matrix_keys"])
            require(len(name.encode("utf-8")) <= 255, f"Filename too long: {name}")
            require(name.casefold() not in planned, f"Filename collision: {name}")
            if not overwrite:
                require(not os.path.lexists(output / name), f"Output already exists: {output / name}")
            planned.add(name.casefold())
            variant["filenames"].append(name)
    return config, source, output, variants


def load_freecad():
    try:
        return importlib.import_module("FreeCAD")
    except ModuleNotFoundError as error:
        if error.name != "FreeCAD":
            raise
    for directory in ("/usr/lib/freecad/lib", "/usr/lib/freecad-python3/lib",
                      "/usr/local/lib/freecad/lib"):
        if Path(directory).is_dir():
            sys.path.append(directory)
    try:
        return importlib.import_module("FreeCAD")
    except ImportError as error:
        raise RuntimeError("Cannot load FreeCAD. See the script header for Python dependencies and PYTHONPATH.") from error


def resolve_label(document, label):
    matches = document.getObjectsByLabel(label)
    require(len(matches) == 1,
            f"Label {label!r}: expected exactly one object, found {len(matches)}"
            + (f" ({', '.join(obj.Name for obj in matches)})" if matches else ""))
    return matches[0]


def check_source_labels(source, entries):
    # Validate every requested label before loading geometry or staging exports.
    # The runtime check also protects against label changes during restoration.
    with zipfile.ZipFile(source) as archive:
        tree = ET.fromstring(archive.read("Document.xml"))
    labels = {}
    for obj in tree.findall("./ObjectData/Object"):
        label = obj.find("./Properties/Property[@name='Label']/String")
        if label is not None:
            labels.setdefault(label.get("value"), []).append(obj.get("name"))
    for index, variant in enumerate(entries, 1):
        for label in {*(key[0] for key in variant["values"]), *variant["objects"]}:
            matches = labels.get(label, [])
            require(len(matches) == 1,
                    f"Entry {index}: label {label!r} in source: expected exactly one object, "
                    f"found {len(matches)} ({', '.join(matches)})")


@contextmanager
def screenshot_session():
    # Importing the GUI into this Python process cannot forward commands to an
    # existing FreeCAD application. Isolate preferences/cache before importing.
    require("FreeCAD" not in sys.modules,
            "Screenshot mode must start in a fresh Python process")
    keys = ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME",
            "QT_QPA_PLATFORM", "LIBGL_ALWAYS_SOFTWARE")
    previous = {key: os.environ.get(key) for key in keys}
    with tempfile.TemporaryDirectory(prefix="freecad-screenshot-profile-") as profile:
        gui = None
        try:
            for key in keys[:3]:
                os.environ[key] = str(Path(profile) / key.lower())
            os.environ["QT_QPA_PLATFORM"] = "xcb"
            os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"
            app = load_freecad()
            # Batch rendering does not need Start's delayed welcome-page UI.
            # Its timer can otherwise fire while a failed worker tears down.
            app.ParamGet("User parameter:BaseApp/Preferences/General").SetString("AutoloadModule", "PartWorkbench")
            app.ParamGet("User parameter:BaseApp/Preferences/Mod/Start").SetBool("ShowOnStartup", False)
            gui = importlib.import_module("FreeCADGui")
            gui.showMainWindow()
            gui.getMainWindow().setWindowTitle("FreeCAD screenshot worker")
            gui.getMainWindow().resize(1600, 1200)
            yield gui
        finally:
            if gui is not None:
                from PySide6 import QtCore, QtWidgets
                gui.getMainWindow().close()
                # Flush deferred view destruction before Python shuts down.
                QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
                QtWidgets.QApplication.processEvents()
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def save_screenshot(app, gui, obj, path, settings):
    # Render a copy of exactly the exported shape, without sketches, origins,
    # other objects or intermediate feature visibility from the source file.
    preview = app.newDocument("ExportPreview")
    try:
        feature = preview.addObject("Part::Feature", "ExportedShape")
        feature.Shape = obj.Shape.copy()
        preview.recompute()
        gui.updateGui()
        view = gui.getDocument(preview.Name).activeView()
        view.viewAxonometric()
        view.fitAll()
        gui.updateGui()
        # Diagnostic settling time: let Qt process paint/resize events instead
        # of blocking rendering with sleep. This is not a GPU completion fence.
        view.redraw()
        from PySide6 import QtCore
        render_wait = QtCore.QEventLoop()
        render_timer = QtCore.QTimer()
        render_timer.setSingleShot(True)
        render_timer.timeout.connect(render_wait.quit)
        render_timer.start(500)
        render_wait.exec()
        view.saveImage(str(path), settings["width"], settings["height"], settings["background"])
    finally:
        app.closeDocument(preview.Name)
        gui.updateGui()


def validate_shape(obj):
    identity = f"Object {obj.Label!r} (internal name: {obj.Name})"
    require(hasattr(obj, "Shape"), f"{identity} has no Shape property")
    shape = obj.Shape
    require(not shape.isNull(), f"{identity} has an empty/null shape")
    if not shape.isValid():
        tip = getattr(obj, "Tip", None)
        detail = f"; tip: {tip.Label!r} ({tip.Name})" if tip is not None else ""
        raise ValueError(
            f"{identity} has invalid geometry (shape.isValid() is False); "
            f"{len(shape.Solids)} solids, {len(shape.Shells)} shells, "
            f"{len(shape.Faces)} faces; status: {obj.getStatusString()}{detail}")


def failed_count(count):
    text = f"{count} failed"
    enabled = "NO_COLOR" not in os.environ and (
        sys.stdout.isatty() or sys.stderr.isatty()
        or os.environ.get("FREECAD_EXPORT_COLOR") == "1")
    if enabled:
        color = 32 if count == 0 else 31
        return f"\033[{color}m{text}\033[0m"
    return text


def failure_details(index, variant, output, stage, error, published):
    lines = [f"Variant {index} ({variant['context']})",
             f"  Stage: {stage}", f"  Error: {type(error).__name__}: {error}",
             "  Outputs:"]
    for label, name in zip(variant["objects"], variant["filenames"]):
        status = "published" if name in published else "not written this run"
        lines.append(f"    {label!r}: {output / name} [{status}]")
    for label, name in zip(variant["objects"], variant.get("cad_filenames", [])):
        status = "published" if name in published else "not written this run"
        lines.append(f"    {label!r}: {Path(variant['cad_output']) / name} [{status}]")
    lines.append("  Effective configured values:")
    for (varset, name), value in sorted(variant["values"].items()):
        lines.append(f"    {varset}.{name} = {value!r}")
    if not variant["values"]:
        lines.append("    (none; original model values)")
    return "\n".join(lines)


def run(config_path, screenshot=False, overwrite=True, prepared=None):
    config, source, output, variants = prepared or read_config(config_path, screenshot, overwrite)
    if config["skipped_screenshots"]:
        print(f"Skipped {config['skipped_screenshots']} variants with screenshot=False.", flush=True)
    if not variants:
        print("No variants enabled for screenshots; nothing to export.", flush=True)
        return
    check_source_labels(source, variants)
    output.mkdir(parents=True, exist_ok=True)
    session = screenshot_session() if screenshot else nullcontext(None)
    with session as gui, tempfile.TemporaryDirectory(prefix=".freecad-export-", dir=output) as staging, ExitStack() as extra_staging:
        app = load_freecad()
        importlib.import_module("Part")
        failures = []
        succeeded = 0
        for index, variant in enumerate(variants, 1):
            document = None
            staged = []
            published = set()
            stage = "opening source model"
            try:
                document = app.openDocument(str(source))
                labels = variant["objects"]
                cad_output = Path(variant["cad_output"]) if "cad_output" in variant else None
                if cad_output is not None:
                    cad_output.mkdir(parents=True, exist_ok=True)
                    cad_staging = Path(extra_staging.enter_context(
                        tempfile.TemporaryDirectory(prefix=".freecad-export-", dir=cad_output)))
                stage = "resolving object labels"
                objects = [resolve_label(document, label) for label in labels]
                for (varset_label, name), value in variant["values"].items():
                    stage = f"setting {varset_label}.{name} = {value!r}"
                    varset = resolve_label(document, varset_label)
                    require(varset.TypeId == "App::VarSet", f"{varset.Label!r} is not a VarSet")
                    require(name in varset.PropertiesList and name not in
                            {"Label", "Label2", "Visibility", "ExpressionEngine"},
                            f"Unknown variable {name!r} in VarSet {varset.Label!r}")
                    varset.setExpression(name, None)
                    try:
                        setattr(varset, name, value)
                    except Exception as error:
                        raise ValueError(f"Cannot set {name} to {value!r}: {error}") from error
                stage = "recomputing model"
                document.recompute()
                invalid = [f"{obj.Label}: {obj.getStatusString()}" for obj in document.Objects
                           if "Invalid" in obj.State or "Error" in obj.State]
                require(not invalid, f"Recompute failed for: {invalid}")
                for object_index, (label, obj, name) in enumerate(zip(labels, objects, variant["filenames"])):
                    stage = f"validating shape of {label!r}"
                    validate_shape(obj)
                    if cad_output is not None:
                        cad_name = variant["cad_filenames"][object_index]
                        stage = f"exporting CAD: {cad_name}"
                        cad_path = cad_staging / cad_name
                        getattr(obj.Shape, EXPORTERS[config["file_extension"]])(str(cad_path))
                        require(cad_path.is_file() and cad_path.stat().st_size > 0,
                                f"Exporter created no data: {cad_name}")
                        staged.append((cad_path, cad_output / cad_name))
                    path = Path(staging) / name
                    stage = f"{'rendering screenshot' if screenshot else 'exporting CAD'}: {name}"
                    if screenshot:
                        save_screenshot(app, gui, obj, path, config["screenshots"])
                    else:
                        getattr(obj.Shape, EXPORTERS[config["file_extension"]])(str(path))
                    require(path.is_file() and path.stat().st_size > 0, f"Exporter created no data: {name}")
                    staged.append((path, output / path.name))
                    print(f"Variant {index}: prepared {name}", flush=True)
                for path, destination in staged:
                    stage = f"publishing {path.name}"
                    # Replace only after a complete export has been staged.
                    if overwrite:
                        os.replace(path, destination)
                    else:
                        os.link(path, destination)
                    published.add(path.name)
                    print(f"Exported {destination}", flush=True)
                succeeded += 1
            except Exception as error:
                failures.append(failure_details(index, variant, output, stage, error, published))
                print(f"Failed: Variant {index}, {stage}: {error}", file=sys.stderr, flush=True)
            finally:
                if document is not None:
                    app.closeDocument(document.Name)
        summary = f"{succeeded}/{len(variants)} variants succeeded; {failed_count(len(failures))}."
        if failures:
            raise RuntimeError(summary + " Successful outputs were retained.\n\n" + "\n\n".join(failures))
        print(summary, flush=True)


def print_plan(config_path):
    config, source, output, variants = read_config(config_path)
    print(f"Dry run: {len(variants)} permutations, "
          f"{sum(len(v['filenames']) for v in variants)} {config['file_extension'].upper()} files.")
    print(f"Source: {source}")
    for index, variant in enumerate(variants, 1):
        print(f"Permutation {index} ({variant['context']}):")
        for (varset, name), value in sorted(variant["values"].items()):
            print(f"  {varset}.{name} = {value!r}")
        for label, name in zip(variant["objects"], variant["filenames"]):
            print(f"  {label!r} -> {output / name}")
    print("Nothing written; geometry has not been recomputed or validated.")


def run_worker(path):
    task = json.loads(path.read_text())
    variant = task["variant"]
    variant["values"] = {(label, name): value for label, name, value in variant["values"]}
    run(None, screenshot=task["screenshot"], overwrite=task["overwrite"], prepared=(
        task["config"], Path(task["source"]), Path(task["output"]), [variant]))


def plan_tasks(config_path, export_models, screenshots, overwrite=True):
    tasks = []
    for screenshot in ([False] if export_models else []) + ([True] if screenshots else []):
        config, source, output, variants = read_config(config_path, screenshot, overwrite)
        check_source_labels(source, variants)
        if config["skipped_screenshots"]:
            print(f"Skipped {config['skipped_screenshots']} variants with screenshot=False.", flush=True)
        for variant in variants:
            encoded = dict(variant)
            encoded["values"] = [[label, name, value] for (label, name), value in variant["values"].items()]
            tasks.append(dict(config=dict(config, skipped_screenshots=0), source=str(source),
                              output=str(output), variant=encoded, screenshot=screenshot, overwrite=overwrite))
    if export_models and screenshots:
        def identity(task):
            variant = task["variant"]
            return json.dumps([variant["context"], variant["name"], variant["objects"], variant["values"]])
        cad_tasks = {identity(task): task for task in tasks if not task["screenshot"]}
        paired = []
        for task in tasks:
            if task["screenshot"]:
                cad = cad_tasks.pop(identity(task))
                task["variant"]["cad_output"] = cad["output"]
                task["variant"]["cad_filenames"] = cad["variant"]["filenames"]
                paired.append(task)
        tasks = list(cad_tasks.values()) + paired
    return tasks


def run_parallel(config_path, export_models, screenshots, jobs=4, overwrite=True):
    parallel = shutil.which("parallel")
    require(parallel is not None, "GNU Parallel is required; install the parallel package")
    tasks = plan_tasks(config_path, export_models, screenshots, overwrite)
    if not tasks:
        print("No jobs enabled; nothing to export.")
        return 0
    with tempfile.TemporaryDirectory(prefix="freecad-parallel-") as directory:
        directory = Path(directory)
        paths = []
        for index, task in enumerate(tasks, 1):
            path = directory / f"job-{index}.json"
            path.write_text(json.dumps(task))
            paths.append(str(path))
        env = dict(os.environ, PARALLEL_HOME=str(directory / "parallel-home"))
        # Parallel captures worker output, so propagate the parent's terminal
        # color setting instead of relying on workers' redirected streams.
        if "NO_COLOR" not in os.environ and (sys.stdout.isatty() or sys.stderr.isatty()):
            env["FREECAD_EXPORT_COLOR"] = "1"
        # Our PARALLEL is a worker count; GNU Parallel uses that name for options.
        env.pop("PARALLEL", None)
        command = shlex.join([sys.executable, str(Path(__file__).resolve()), "--worker", "{}"])
        print(f"Running {len(tasks)} jobs with up to {jobs} workers.", flush=True)
        result = subprocess.run([parallel, "--plain", "--jobs", str(jobs), "--group",
                                 "--halt", "never", "--null", "--joblog", str(directory / "jobs.tsv"),
                                 command], input="\0".join(paths) + "\0", text=True, env=env)
        log = directory / "jobs.tsv"
        if log.is_file():
            rows = [line.split("\t") for line in log.read_text().splitlines()[1:]]
            succeeded = sum(len(row) >= 8 and row[6] == "0" and row[7] == "0" for row in rows)
            print(f"Batch: {succeeded}/{len(tasks)} jobs succeeded; "
                  f"{failed_count(len(rows) - succeeded)}; {len(tasks) - len(rows)} not completed.", flush=True)
            failed_indices = {int(row[0]) - 1 for row in rows
                              if len(row) >= 8 and (row[6] != "0" or row[7] != "0")}
            retained = []
            for index in failed_indices:
                task = tasks[index]
                variant = task["variant"]
                destinations = [Path(task["output"]) / name for name in variant["filenames"]]
                destinations += [Path(variant["cad_output"]) / name
                                 for name in variant.get("cad_filenames", [])]
                retained.extend(path for path in destinations if path.exists())
            if retained:
                print(f"Note: {len(retained)} existing output files belong to failed jobs. "
                      "They were not removed; directory totals may include earlier results.", flush=True)
        if result.returncode:
            print("Some jobs failed; successful outputs were retained. See job diagnostics above.", file=sys.stderr)
        return int(result.returncode != 0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("config", type=Path, nargs="?", help="Configuration file; without mode flags, list permutations only")
    parser.add_argument("-e", "--export", action="store_true", help="Export 3D model files in the configured format")
    parser.add_argument("-s", "--screenshot", action="store_true", help="Create PNG previews")
    parser.add_argument("-p", "--parallel", "--paralell", type=int, default=None,
                        help="Maximum concurrent workers: CLI overrides exported PARALLEL; otherwise 4")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--overwrite", action=argparse.BooleanOptionalAction, default=True,
                        help="Replace existing output files (default: enabled)")
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    if args.parallel is None:
        try:
            args.parallel = int(os.environ.get("PARALLEL", "4"))
        except ValueError:
            parser.error("PARALLEL must be a positive integer (or override it with --parallel)")
    if args.parallel < 1:
        parser.error("--parallel/PARALLEL must be a positive integer")
    if args.worker is not None:
        try:
            run_worker(args.worker)
            return 0
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1
    if args.config is None:
        parser.error("a configuration file is required")
    try:
        config_path = args.config.resolve()
        if args.export or args.screenshot:
            return run_parallel(config_path, args.export, args.screenshot, args.parallel, args.overwrite)
        else:
            print_plan(config_path)
    except Exception as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
