# Relative paths are resolved from this configuration file's directory.
source_filename = "case.FCStd"
file_extension = "step"
file_prefix = ""
output_directory = "exports/case/"
# FreeCAD reports the top and bottom solids as invalid despite valid object
# status. Export these non-null shapes and let the STEP exporter report errors.
ignore_geometry_validity = True

# Used only with --screenshot. Paths are relative to this config file.
# PNGs share the CAD filename stem; the normal FreeCAD profile is not used.
screenshots = {
    "output_directory": output_directory + "/images/",
    "width": 1600,
    "height": 1200,
    "background": "#404040",  # #RRGGBB or "Transparent"
    "screenshot": False,  # Groups must explicitly enable screenshots.
}

exports = [
    {
        # Keys under values are visible VarSet labels. Additional VarSets can be
        # added alongside parameters; their axes join the same cross product.
        "matrix": {
            "values": {
                "parameters": {
                },
            },
        },
        "objects": ["top", "bottom"],
        "groups": [
            {
                # Cable section 2.4 x 7.6 mm; configured slot width is 2.5 mm.
                # Effective matrix variables are appended automatically.
                "name": "{object}",
                "screenshot": True,  # Overrides the default in screenshots above.
                "values": {
                    "parameters": {
                    },
                },
            },
        ],
    },
]
