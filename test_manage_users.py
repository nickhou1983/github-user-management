import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import manage_users


class UserCsvTests(unittest.TestCase):
    def test_read_usernames_reads_username_column_and_ignores_blank_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "users.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=["username", "note"])
                writer.writeheader()
                writer.writerow({"username": " monalisa ", "note": "ok"})
                writer.writerow({"username": "", "note": "skip"})
                writer.writerow({"username": "octocat", "note": "ok"})

            self.assertEqual(manage_users.read_usernames(csv_path), ["monalisa", "octocat"])

    def test_read_usernames_requires_username_column(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            csv_path = Path(temp_dir) / "users.csv"
            csv_path.write_text("login\nmonalisa\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "username"):
                manage_users.read_usernames(csv_path)


class OperationTests(unittest.TestCase):
    def test_add_to_enterprise_team_dry_run_does_not_call_api(self):
        client = Mock()

        summary = manage_users.add_to_enterprise_team(
            client=client,
            enterprise="octo-enterprise",
            team="engineering",
            usernames=["monalisa", "octocat"],
            dry_run=True,
        )

        self.assertEqual(summary.skipped, 2)
        client.post.assert_not_called()

    def test_add_to_cost_center_dry_run_does_not_call_api(self):
        client = Mock()

        summary = manage_users.add_to_cost_center(
            client=client,
            enterprise="octo-enterprise",
            cost_center_id="cc-123",
            usernames=["monalisa", "octocat"],
            dry_run=True,
        )

        self.assertEqual(summary.skipped, 2)
        client.post.assert_not_called()

    def test_add_to_cost_center_dry_run_with_name_does_not_call_api(self):
        client = Mock()

        summary = manage_users.add_to_cost_center(
            client=client,
            enterprise="octo-enterprise",
            cost_center="Engineering",
            usernames=["monalisa", "octocat"],
            dry_run=True,
        )

        self.assertEqual(summary.skipped, 2)
        client.get.assert_not_called()
        client.post.assert_not_called()

    def test_remove_from_org_requires_yes_confirmation_before_calling_api(self):
        client = Mock()

        summary = manage_users.remove_from_org(
            client=client,
            org="octo-org",
            usernames=["monalisa", "octocat"],
            dry_run=False,
            confirm=lambda _: "no",
        )

        self.assertEqual(summary.skipped, 2)
        client.delete.assert_not_called()

    def test_remove_from_org_deletes_each_user_after_confirmation(self):
        client = Mock()
        client.delete.return_value = manage_users.ApiResponse(status_code=204, data=None, message="No Content")

        summary = manage_users.remove_from_org(
            client=client,
            org="octo-org",
            usernames=["monalisa", "octocat"],
            dry_run=False,
            confirm=lambda _: "yes",
        )

        self.assertEqual(summary.success, 2)
        client.delete.assert_any_call("/orgs/octo-org/members/monalisa")
        client.delete.assert_any_call("/orgs/octo-org/members/octocat")

    def test_list_non_owner_org_members_uses_member_role_filter(self):
        client = Mock()
        client.get.side_effect = [
            manage_users.ApiResponse(
                status_code=200,
                data=[{"login": "monalisa"}, {"login": "octocat"}],
                message="OK",
            ),
            manage_users.ApiResponse(status_code=200, data=[], message="OK"),
        ]

        members = manage_users.list_non_owner_org_members(client, "octo-org")

        self.assertEqual(members, ["monalisa", "octocat"])
        client.get.assert_any_call("/orgs/octo-org/members?role=member&per_page=100&page=1")
        client.get.assert_any_call("/orgs/octo-org/members?role=member&per_page=100&page=2")

    def test_remove_non_owners_from_org_lists_members_and_deletes_after_confirmation(self):
        client = Mock()
        client.get.side_effect = [
            manage_users.ApiResponse(
                status_code=200,
                data=[{"login": "monalisa"}, {"login": "octocat"}],
                message="OK",
            ),
            manage_users.ApiResponse(status_code=200, data=[], message="OK"),
        ]
        client.delete.return_value = manage_users.ApiResponse(status_code=204, data=None, message="No Content")

        summary = manage_users.remove_non_owners_from_org(
            client=client,
            org="octo-org",
            dry_run=False,
            confirm=lambda _: "yes",
        )

        self.assertEqual(summary.success, 2)
        client.delete.assert_any_call("/orgs/octo-org/members/monalisa")
        client.delete.assert_any_call("/orgs/octo-org/members/octocat")

    def test_remove_non_owners_from_org_dry_run_does_not_delete(self):
        client = Mock()
        client.get.side_effect = [
            manage_users.ApiResponse(status_code=200, data=[{"login": "monalisa"}], message="OK"),
            manage_users.ApiResponse(status_code=200, data=[], message="OK"),
        ]

        summary = manage_users.remove_non_owners_from_org(
            client=client,
            org="octo-org",
            dry_run=True,
        )

        self.assertEqual(summary.skipped, 1)
        client.delete.assert_not_called()

    def test_add_to_enterprise_team_uses_bulk_membership_api(self):
        client = Mock()
        client.post.return_value = manage_users.ApiResponse(status_code=200, data=[], message="OK")

        summary = manage_users.add_to_enterprise_team(
            client=client,
            enterprise="octo-enterprise",
            team="engineering",
            usernames=["monalisa", "octocat"],
            dry_run=False,
        )

        self.assertEqual(summary.success, 2)
        client.post.assert_called_once_with(
            "/enterprises/octo-enterprise/teams/engineering/memberships/add",
            {"usernames": ["monalisa", "octocat"]},
        )

    def test_add_to_cost_center_uses_bulk_resource_api(self):
        client = Mock()
        client.post.return_value = manage_users.ApiResponse(status_code=200, data={}, message="OK")

        summary = manage_users.add_to_cost_center(
            client=client,
            enterprise="octo-enterprise",
            cost_center_id="cc-123",
            usernames=["monalisa", "octocat"],
            dry_run=False,
        )

        self.assertEqual(summary.success, 2)
        client.post.assert_called_once_with(
            "/enterprises/octo-enterprise/settings/billing/cost-centers/cc-123/resource",
            {"users": ["monalisa", "octocat"]},
        )

    def test_add_to_cost_center_resolves_cost_center_name_to_id(self):
        client = Mock()
        client.get.return_value = manage_users.ApiResponse(
            status_code=200,
            data={
                "costCenters": [
                    {"id": "cc-id-1", "name": "Engineering", "state": "active"},
                    {"id": "cc-id-2", "name": "HR", "state": "active"},
                ]
            },
            message="OK",
        )
        client.post.return_value = manage_users.ApiResponse(status_code=200, data={}, message="OK")

        summary = manage_users.add_to_cost_center(
            client=client,
            enterprise="octo-enterprise",
            cost_center="Engineering",
            usernames=["monalisa", "octocat"],
            dry_run=False,
        )

        self.assertEqual(summary.success, 2)
        client.get.assert_called_once_with("/enterprises/octo-enterprise/settings/billing/cost-centers")
        client.post.assert_called_once_with(
            "/enterprises/octo-enterprise/settings/billing/cost-centers/cc-id-1/resource",
            {"users": ["monalisa", "octocat"]},
        )


class FailureReportTests(unittest.TestCase):
    def test_write_failures_removes_stale_report_when_there_are_no_failures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "failed_users.csv"
            report_path.write_text("username,status_code,message\nold,403,Forbidden\n", encoding="utf-8")

            manage_users.write_failures(report_path, [])

            self.assertFalse(report_path.exists())


class CliTests(unittest.TestCase):
    def test_config_file_supplies_common_and_command_arguments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "csv": "users.csv",
                        "enterprise": "octo-enterprise",
                        "dry_run": True,
                        "add_to_team": {"team": "engineering"},
                    }
                ),
                encoding="utf-8",
            )
            args = manage_users.build_parser().parse_args(["--config", str(config_path), "add-to-team"])

            resolved = manage_users.apply_config(args)

            self.assertEqual(resolved.csv_path, "users.csv")
            self.assertEqual(resolved.enterprise, "octo-enterprise")
            self.assertTrue(resolved.dry_run)
            self.assertEqual(resolved.team, "engineering")

    def test_remove_non_owners_from_org_does_not_require_csv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "token": "dummy-token",
                        "remove_non_owners_from_org": {"org": "octo-org"},
                    }
                ),
                encoding="utf-8",
            )
            args = manage_users.build_parser().parse_args(
                ["--config", str(config_path), "remove-non-owners-from-org", "--dry-run"]
            )

            resolved = manage_users.apply_config(args)

            self.assertEqual(resolved.org, "octo-org")
            self.assertIsNone(getattr(resolved, "csv_path", None))

    def test_config_file_supplies_cost_center_name(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "csv": "users.csv",
                        "enterprise": "octo-enterprise",
                        "add_to_cost_center": {"cost_center": "Engineering"},
                    }
                ),
                encoding="utf-8",
            )
            args = manage_users.build_parser().parse_args(["--config", str(config_path), "add-to-cost-center"])

            resolved = manage_users.apply_config(args)

            self.assertEqual(resolved.cost_center, "Engineering")

    def test_command_line_arguments_override_config_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "csv": "from-config.csv",
                        "enterprise": "from-config",
                        "add_to_team": {"team": "from-config-team"},
                    }
                ),
                encoding="utf-8",
            )
            args = manage_users.build_parser().parse_args(
                [
                    "--config",
                    str(config_path),
                    "add-to-team",
                    "--csv",
                    "from-cli.csv",
                    "--enterprise",
                    "from-cli",
                    "--team",
                    "from-cli-team",
                ]
            )

            resolved = manage_users.apply_config(args)

            self.assertEqual(resolved.csv_path, "from-cli.csv")
            self.assertEqual(resolved.enterprise, "from-cli")
            self.assertEqual(resolved.team, "from-cli-team")

    def test_common_options_can_appear_after_subcommand(self):
        args = manage_users.build_parser().parse_args(
            [
                "add-to-team",
                "--csv",
                "users.csv",
                "--enterprise",
                "octo-enterprise",
                "--dry-run",
                "--team",
                "engineering",
            ]
        )

        self.assertEqual(args.command, "add-to-team")
        self.assertEqual(args.csv_path, "users.csv")
        self.assertEqual(args.enterprise, "octo-enterprise")
        self.assertTrue(args.dry_run)


if __name__ == "__main__":
    unittest.main()