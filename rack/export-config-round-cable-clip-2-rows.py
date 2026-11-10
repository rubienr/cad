# Relative paths are resolved from this configuration file's directory.
source_filename = "round-cable-clip-2-rows.FCStd"
file_extension = "step"
file_prefix = ""
output_directory = "exports/round-cable-clip-2-rows/"

# Used only with --screenshot. Paths are relative to this config file.
# PNGs share the CAD filename stem; the normal FreeCAD profile is not used.
screenshots = {
    "output_directory": "exports/round-cable-clip-2-rows/images/",
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
                    "hole_separation": ["0 mm", "1 mm"],
                    "holes": [2, 3, 4, 5],
                    "length": ["10 mm"],
                },
            },
        },
        "objects": ["clip"],
        "groups": [
            {
                # Effective matrix variables are appended automatically.
                "name": "{object}-4.1mm",
                "screenshot": True,  # Overrides the default in screenshots above.
                "values": {
                    "parameters": {
                        "hole_diameter": "4.1 mm",
                    },
                },
            },
            {
                "name": "{object}-6.5mm",
                "screenshot": True,  # Overrides the default in screenshots above.
                "values": {
                    "parameters": {
                        "hole_diameter": "6.5 mm",
                    },
                },
            },
        ],
    },
]
