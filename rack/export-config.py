# Relative paths are resolved from this configuration file's directory.
source_filename = "flat-lan-cable-clip.FCStd"
file_extension = "step"
file_prefix = ""
output_directory = "exports/"

# Used only with --screenshot. Paths are relative to this config file.
# PNGs share the CAD filename stem; the normal FreeCAD profile is not used.
screenshots = {
    "output_directory": "exports/images/",
    "width": 1600,
    "height": 1200,
    "background": "#404040",  # #RRGGBB or "Transparent"
    "screenshot": False,  # Groups must explicitly enable screenshots.
}

exports = {
    # Keys under values are visible VarSet labels. Additional VarSets can be
    # added alongside parameters; their axes join the same cross product.
    "matrix": {
        "values": {
            "parameters": {
                "slot_separation": ["0 mm", "1 mm"],
                "length": ["10 mm", "15 mm"],
                "slots": [2, 3, 4, 5, 6, 7, 8, 9, 10],
            },
        },
    },
    "objects": ["clip"],
    "groups": [
        {
            # Cable section 2.4 x 7.6 mm; configured slot width is 2.5 mm.
            # Effective matrix variables are appended automatically.
            "name": "{object}-2.4x7.6",
            "screenshot": True,  # Overrides the default in screenshots above.
            "values": {
                "parameters": {
                    "slot_width": "2.5 mm",
                    "slot_height": "7.6 mm",
                },
            },
        },
        {
            "name": "{object}-1.6x6.4",
            "screenshot": False,
            "values": {
                "parameters": {
                    "slot_width": "1.6 mm",
                    "slot_height": "6.4 mm",
                },
            },
        },
    ],
}
