# Relative paths are resolved from this configuration file's directory.
source_filename = "hanging-bracket-for-monitor.FCStd"
file_extension = "step"
file_prefix = ""
output_directory = "exports/hanging-bracket/"

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
                    "bracket_distance": ["100 mm"],
                },
            },
        },
        "objects": ["spacer"],
        "groups": [
            {
                "name": "{object}",
                "screenshot": True,
                "values": { },
            },
        ],
    },
]
