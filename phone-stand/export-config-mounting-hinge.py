# Relative paths are resolved from this configuration file's directory.
source_filename = "hanging-bracket-for-monitor.FCStd"
file_extension = "step"
file_prefix = ""
output_directory = "exports/mounting/"

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
                    "bracket_width": ["12 mm"],
                    "hinge_bore_dia": ["0.8 mm"],
                    "thickness": ["5 mm"],
                },
            },
        },
        "objects": ["mounting-hinge"],
        "groups": [
            {
                "name": "{object}",
                "screenshot": True,
                "values": { },
            },
        ],
    },
    {
        "matrix": {
            "values": {
                "parameters": {
                    "bracket_width": ["12 mm"],
                    "hinge_bore_dia": ["1.9 mm"],
                    "thickness": ["5 mm"],
                    "screw_bore_dia": ["2.5 mm"],
                    "screw_head_dia": ["5.4 mm"],
                    "screw_head_inset": ["1 mm"],
                },
            },
        },
        "objects": ["mounting-hinge-whith-mounting-holes"],
        "groups": [
            {
                "name": "{object}",
                "screenshot": True,
                "values": { },
            },
        ],
    },
    {
        "matrix": {
            "values": {
                "parameters": {
                    "bracket_width": ["12 mm"],
                    "hinge_bore_dia": ["1.9 mm"],
                    "thickness": ["5 mm"],
                    "curved_monitor_radius": ["1.0 m", "1.5 m", "1.7 m", "1.8 m", "1.9 m", "2.0 m", "2.5m", "3.4m", "3.8 m"],
                },
            },
        },
        "objects": ["mounting-hinge-for-curved-monitor"],
        "groups": [
            {
                "name": "{object}",
                "screenshot": True,
                "values": { },
            },
        ],
    },
]
