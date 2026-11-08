"""Matrix/config regression tests; run with python3 -B -m unittest -v."""
import copy
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

import export


class MatrixTests(unittest.TestCase):
    def test_global_screenshot_default_and_group_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="",
                          screenshots={"screenshot": False},
                          exports={"objects": ["clip"], "groups": [
                              {"name": "inherited"},
                              {"name": "enabled", "screenshot": True},
                              {"name": "disabled", "screenshot": False},
                          ]})
            path = base / "config.py"
            for default, expected in ((False, ["enabled"]),
                                      (True, ["inherited", "enabled"])):
                config["screenshots"]["screenshot"] = default
                path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
                variants = export.read_config(path, screenshot=True)[3]
                self.assertEqual([v["name"] for v in variants], expected)
                self.assertEqual(len(export.read_config(path)[3]), 3)

    def test_screenshot_group_inheritance(self):
        group = {"name": "clip", "objects": ["clip"], "groups": [
            {}, {"screenshot": False, "groups": [{}, {"screenshot": True}]},
        ]}
        self.assertEqual([v["screenshot"] for v in export.expand_groups(group)],
                         [True, False, True])
        group["screenshot"] = "false"
        with self.assertRaisesRegex(ValueError, "screenshot must be"):
            list(export.expand_groups(group))

    def test_suppressed_screenshots_do_not_affect_cad(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="",
                          exports={"name": "clip", "objects": ["clip"], "screenshot": False})
            path = base / "config.py"
            path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
            self.assertEqual(len(export.read_config(path)[3]), 1)
            parsed, _, _, variants = export.read_config(path, screenshot=True)
            self.assertEqual(variants, [])
            self.assertEqual(parsed["skipped_screenshots"], 1)
            export.run(path, screenshot=True)  # No CAD loading or GUI startup.

    def test_failure_summary_identifies_values_outputs_and_stage(self):
        variant = {"context": "exports.groups[1]", "objects": ["clip", "other"],
                   "filenames": ["clip-slots-2.png", "other-slots-2.png"],
                   "values": {("parameters", "slots"): 2,
                              ("parameters", "slot_width"): "2.5 mm"}}
        report = export.failure_details(1, variant, Path("/tmp/images"),
                                        "validating shape of 'clip'", ValueError("invalid geometry"),
                                        {"other-slots-2.png"})
        for text in ("exports.groups[1]", "validating shape", "ValueError: invalid geometry",
                     "parameters.slots = 2", "parameters.slot_width = '2.5 mm'",
                     "/tmp/images/clip-slots-2.png [not written this run]",
                     "/tmp/images/other-slots-2.png [published]"):
            self.assertIn(text, report)

    def test_shape_error_distinguishes_empty_and_invalid(self):
        obj = SimpleNamespace(Label="clip", Name="Body")
        with self.assertRaisesRegex(ValueError, "no Shape property"):
            export.validate_shape(obj)
        obj.Shape = SimpleNamespace(isNull=lambda: True)
        with self.assertRaisesRegex(ValueError, "empty/null"):
            export.validate_shape(obj)
        obj.Shape = SimpleNamespace(isNull=lambda: False, isValid=lambda: False,
                                    Solids=[1], Shells=[1], Faces=[1, 2])
        obj.getStatusString = lambda: "Up-to-date"
        obj.Tip = SimpleNamespace(Label="Fillet", Name="Fillet001")
        with self.assertRaisesRegex(ValueError, "1 solids, 1 shells, 2 faces.*Fillet001"):
            export.validate_shape(obj)

    def setUp(self):
        self.group = {
            "name": "{object}-{parameters.x}-{mounting.y}",
            "objects": ["clip"],
            "matrix": {"values": {
                "parameters": {"x": [1, 2]},
                "mounting": {"y": [3, 4]},
            }},
        }

    def test_cross_product_across_varsets(self):
        variants = list(export.expand_groups(self.group))
        self.assertEqual({(v["values"]["parameters", "x"], v["values"]["mounting", "y"])
                          for v in variants}, {(1, 3), (1, 4), (2, 3), (2, 4)})

    def test_nested_overrides_before_expansion_and_sibling_isolation(self):
        self.group["groups"] = [
            {"values": {"parameters": {"x": 9}}, "groups": [
                {"matrix": {"values": {"mounting": {"y": [8]}}}},
            ]},
            {},
        ]
        before = copy.deepcopy(self.group)
        variants = list(export.expand_groups(self.group))
        self.assertEqual(len(variants), 5)
        self.assertEqual(variants[0]["values"], {("parameters", "x"): 9, ("mounting", "y"): 8})
        self.assertEqual(variants[0]["matrix_keys"], [("mounting", "y")])
        self.assertEqual(variants[1]["matrix_keys"], [("mounting", "y"), ("parameters", "x")])
        self.assertEqual(self.group, before)

    def test_inner_matrix_replaces_fixed_value_and_objects(self):
        group = {"name": "{object}-{p.x}", "objects": ["outer"],
                 "values": {"p": {"x": 1}}, "groups": [
                     {"objects": ["inner"], "matrix": {"values": {"p": {"x": [2, 3]}}}},
                 ]}
        variants = list(export.expand_groups(group))
        self.assertEqual([v["values"]["p", "x"] for v in variants], [2, 3])
        self.assertTrue(all(v["objects"] == ["inner"] for v in variants))
        self.assertTrue(all(v["matrix_keys"] == [("p", "x")] for v in variants))

    def test_automatic_matrix_suffix(self):
        group = {"name": "{object}-1.4x6.1", "objects": ["clip"],
                 "values": {"parameters": {"slot_width": "1.4 mm"}},
                 "matrix": {"values": {"parameters": {
                     "slot_separation": ["0 mm", "1 mm"],
                     "length": ["10 mm", "15 mm"],
                 }}}}
        names = [export.filename("", v["name"], "clip", v["values"], "step", v["matrix_keys"])
                 for v in export.expand_groups(group)]
        self.assertEqual(set(names), {
            f"clip-1.4x6.1-length-{length}_mm_slot_separation-{spacing}_mm.step"
            for length in (10, 15) for spacing in (0, 1)})

    def test_duplicate_axis_names_are_qualified(self):
        values = {("b", "size"): 2, ("a", "size"): 1, ("a", "length"): 3}
        self.assertEqual(export.filename("", "clip", "clip", values, "png", values),
                         "clip-length-3_a.size-1_b.size-2.png")

    def test_conflicting_definitions(self):
        self.group["values"] = {"parameters": {"x": 5}}
        with self.assertRaisesRegex(ValueError, "both values and matrix"):
            list(export.expand_groups(self.group))

    def test_empty_axis_rejected(self):
        self.group["matrix"]["values"]["parameters"]["x"] = []
        with self.assertRaisesRegex(ValueError, "nonempty candidate list"):
            list(export.expand_groups(self.group))

    def test_empty_overrides_and_template(self):
        variants = list(export.expand_groups({"name": "plain", "objects": ["clip"]}))
        self.assertEqual(len(variants), 1)
        self.assertEqual(variants[0]["values"], {})
        self.assertEqual(export.filename("foo_", "{object}-{p.x}", "clip", {("p", "x"): "1 mm"}, "step"),
                         "foo_clip-1_mm.step")
        with self.assertRaisesRegex(ValueError, "Unknown name template field"):
            export.filename("", "{p.missing}", "clip", {}, "step")

    def test_collision_after_sanitization(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="", exports={
                              "name": "{p.x}", "objects": ["clip"],
                              "matrix": {"values": {"p": {"x": ["a b", "a/b"]}}},
                          })
            path = base / "config.py"
            path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
            with self.assertRaisesRegex(ValueError, "Filename collision"):
                export.read_config(path)

    def test_screenshot_checks_png_collisions_independently(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            (base / "out").mkdir()
            (base / "out/clip.step").touch()
            config = dict(source_filename="model.FCStd", output_directory="out",
                          file_extension="step", file_prefix="",
                          screenshots={"output_directory": "out"},
                          exports={"name": "clip", "objects": ["clip"]})
            path = base / "config.py"
            path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))
            _, _, _, variants = export.read_config(path, screenshot=True)
            self.assertEqual(variants[0]["filenames"], ["clip.png"])
            export.read_config(path)  # Existing CAD output is allowed by default.
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                export.read_config(path, overwrite=False)
            (base / "out/clip.png").touch()
            export.read_config(path, screenshot=True)
            with self.assertRaisesRegex(ValueError, "Output already exists"):
                export.read_config(path, screenshot=True, overwrite=False)

    def test_screenshot_settings_and_relative_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "model.FCStd").touch()
            config = dict(source_filename="model.FCStd", output_directory="cad",
                          file_extension="step", file_prefix="",
                          screenshots={"output_directory": "previews", "width": 800,
                                       "height": 600, "background": "#505050"},
                          exports={"name": "clip", "objects": ["clip"]})
            path = base / "config.py"

            def write():
                path.write_text("\n".join(f"{key} = {value!r}" for key, value in config.items()))

            write()
            parsed, _, output, _ = export.read_config(path, screenshot=True)
            self.assertEqual(output, base / "previews")
            self.assertEqual(parsed["screenshots"], {"screenshot": True, **config["screenshots"]})
            self.assertEqual(export.read_config(path)[2], base / "cad")
            for key, value in (("width", True), ("height", 0), ("background", "invalid"),
                               ("output_directory", "")):
                with self.subTest(key=key):
                    previous = config["screenshots"][key]
                    config["screenshots"][key] = value
                    write()
                    with self.assertRaisesRegex(ValueError, "screenshots"):
                        export.read_config(path, screenshot=True)
                    config["screenshots"][key] = previous


if __name__ == "__main__":
    unittest.main()
