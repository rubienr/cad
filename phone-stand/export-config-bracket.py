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
                    "bracket_knick_angle": ["130 °"],
                    "bracket_knick_length": ["30 mm"],
                    "bracket_width": ["12 mm"],
                    "dent_length": ["3 mm"],
                    "dent_slant": ["110 °"],
                    "hinge_bore_dia": ["0.8 mm"],
                    "phone_thickness": ["10 mm"],
                    "phone_width": ["75 mm"],
                    "thickness": ["5 mm"],
                },
            },
        },
        "objects": ["bracket"],
        "groups": [
            {
                "name": "{object}",
                "screenshot": True,
            },
        ],
    },
    {
        "matrix": {
            "values": {
                "parameters": {
                    "bracket_distance": ["100 mm"], # spacer (inner distance in-between brackets)
                    "bracket_knick_angle": ["130 °"],
                    "bracket_knick_length": ["30 mm"],
                    "bracket_width": ["12 mm"],
                    "dent_length": ["3 mm"],
                    "dent_slant": ["110 °"],
                    "hinge_bore_dia": ["0.8 mm"],
                    "phone_thickness": ["10 mm"],
                    "phone_width": ["75 mm"],
                    "spacer_pocket_depth": ["5 mm"], # pocket
                    "thickness": ["5 mm"],
                },
            },
        },
        "objects": ["bracket-with-spacer-pocket"],
        "groups": [
            {
                "name": "bracket-with-spacer-pocket",
                "screenshot": True,
            },
        ],
    },
]
