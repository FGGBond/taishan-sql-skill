import unittest

from big_data_sql.project_info import extract_local_project


class ProjectInfoTests(unittest.TestCase):
    def test_extract_local_project_success(self) -> None:
        result = {
            "success": True,
            "code": 0,
            "obj": {
                "gitProjectId": "1000669346",
                "gitProjectName": "DQ-example.erp",
                "hasAuthority": False,
            },
        }
        project = extract_local_project(result)
        assert project is not None
        self.assertEqual(project["git_project_id"], "1000669346")
        self.assertEqual(project["git_project_name"], "DQ-example.erp")
        self.assertFalse(project["has_authority"])

    def test_extract_local_project_missing(self) -> None:
        self.assertIsNone(extract_local_project({"success": False}))
        self.assertIsNone(extract_local_project({"error_code": "HTTP_ERROR"}))


if __name__ == "__main__":
    unittest.main()
