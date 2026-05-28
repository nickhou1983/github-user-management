#!/usr/bin/env python3
import argparse
import csv
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_VERSION = "2022-11-28"
DEFAULT_BASE_URL = "https://api.github.com"


@dataclass
class ApiResponse:
    status_code: int
    data: Any
    message: str


@dataclass
class Failure:
    username: str
    status_code: int | None
    message: str


@dataclass
class OperationSummary:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[Failure] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.success + self.failed + self.skipped

    def add_failure(self, username: str, status_code: int | None, message: str) -> None:
        self.failed += 1
        self.failures.append(Failure(username=username, status_code=status_code, message=message))


class GitHubApiError(Exception):
    def __init__(self, status_code: int | None, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class GitHubClient:
    def __init__(self, token: str, base_url: str = DEFAULT_BASE_URL, api_version: str = API_VERSION):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version

    def delete(self, path: str) -> ApiResponse:
        return self._request("DELETE", path)

    def get(self, path: str) -> ApiResponse:
        return self._request("GET", path)

    def post(self, path: str, payload: dict[str, Any]) -> ApiResponse:
        return self._request("POST", path, payload)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> ApiResponse:
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")

        request = Request(
            url=f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": self.api_version,
                "Content-Type": "application/json",
                "User-Agent": "github-user-management-script",
            },
        )

        try:
            return self._send(request)
        except HTTPError as error:
            if self._is_rate_limited(error):
                wait_seconds = self._rate_limit_wait_seconds(error)
                if wait_seconds > 0:
                    print(f"Rate limit reached. Waiting {wait_seconds} seconds before retrying...", file=sys.stderr)
                    time.sleep(wait_seconds)
                    return self._send(request)
            raise self._api_error_from_http_error(error) from error
        except URLError as error:
            raise GitHubApiError(None, f"Network error: {error.reason}") from error

    def _send(self, request: Request) -> ApiResponse:
        with urlopen(request) as response:
            raw_body = response.read().decode("utf-8")
            data = json.loads(raw_body) if raw_body else None
            return ApiResponse(status_code=response.status, data=data, message=response.reason)

    @staticmethod
    def _is_rate_limited(error: HTTPError) -> bool:
        return error.code in {403, 429} and error.headers.get("x-ratelimit-remaining") == "0"

    @staticmethod
    def _rate_limit_wait_seconds(error: HTTPError) -> int:
        reset_value = error.headers.get("x-ratelimit-reset")
        if reset_value is None:
            return 0
        try:
            return max(0, int(reset_value) - int(time.time()) + 1)
        except ValueError:
            return 0

    @staticmethod
    def _api_error_from_http_error(error: HTTPError) -> GitHubApiError:
        raw_body = error.read().decode("utf-8")
        message = error.reason
        if raw_body:
            try:
                message = json.loads(raw_body).get("message", raw_body)
            except json.JSONDecodeError:
                message = raw_body
        return GitHubApiError(error.code, message)


def read_usernames(csv_path: str | Path) -> list[str]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        if reader.fieldnames is None or "username" not in reader.fieldnames:
            raise ValueError("CSV file must contain a 'username' column")
        return [row["username"].strip() for row in reader if row.get("username", "").strip()]


def remove_from_org(
    client: GitHubClient,
    org: str,
    usernames: list[str],
    dry_run: bool,
    confirm: Callable[[str], str] = input,
) -> OperationSummary:
    summary = OperationSummary()
    if dry_run:
        for username in usernames:
            print(f"[dry-run] Would remove {username} from organization {org}")
            summary.skipped += 1
        return summary

    prompt = (
        f"This will remove {len(usernames)} user(s) from organization '{org}'. "
        "Type 'yes' to continue: "
    )
    if confirm(prompt).strip() != "yes":
        print("Operation cancelled. No users were removed.")
        summary.skipped = len(usernames)
        return summary

    encoded_org = quote(org, safe="")
    for username in usernames:
        encoded_username = quote(username, safe="")
        try:
            response = client.delete(f"/orgs/{encoded_org}/members/{encoded_username}")
            if response.status_code == 204:
                summary.success += 1
                print(f"Removed {username} from {org}")
            else:
                summary.add_failure(username, response.status_code, response.message)
        except GitHubApiError as error:
            if error.status_code == 404:
                summary.skipped += 1
                print(f"Skipped {username}: not a member of {org}")
            else:
                summary.add_failure(username, error.status_code, error.message)
                print(f"Failed to remove {username}: {error.message}", file=sys.stderr)
    return summary


def list_non_owner_org_members(client: GitHubClient, org: str) -> list[str]:
    encoded_org = quote(org, safe="")
    members: list[str] = []
    page = 1
    while True:
        response = client.get(f"/orgs/{encoded_org}/members?role=member&per_page=100&page={page}")
        if not isinstance(response.data, list) or not response.data:
            break
        for member in response.data:
            login = member.get("login") if isinstance(member, dict) else None
            if login:
                members.append(login)
        page += 1
    return members


def remove_non_owners_from_org(
    client: GitHubClient,
    org: str,
    dry_run: bool,
    confirm: Callable[[str], str] = input,
) -> OperationSummary:
    usernames = list_non_owner_org_members(client, org)
    if not usernames:
        print(f"No non-owner members found in organization {org}.")
        return OperationSummary()
    return remove_from_org(client=client, org=org, usernames=usernames, dry_run=dry_run, confirm=confirm)


def add_to_enterprise_team(
    client: GitHubClient,
    enterprise: str,
    team: str,
    usernames: list[str],
    dry_run: bool,
) -> OperationSummary:
    summary = OperationSummary()
    if dry_run:
        for username in usernames:
            print(f"[dry-run] Would add {username} to enterprise team {team} in {enterprise}")
            summary.skipped += 1
        return summary

    encoded_enterprise = quote(enterprise, safe="")
    encoded_team = quote(team, safe="")
    path = f"/enterprises/{encoded_enterprise}/teams/{encoded_team}/memberships/add"
    try:
        client.post(path, {"usernames": usernames})
        summary.success = len(usernames)
        print(f"Added {len(usernames)} user(s) to enterprise team {team}")
    except GitHubApiError as error:
        for username in usernames:
            summary.add_failure(username, error.status_code, error.message)
        print(f"Failed to add users to enterprise team {team}: {error.message}", file=sys.stderr)
    return summary


def add_to_cost_center(
    client: GitHubClient,
    enterprise: str,
    usernames: list[str],
    dry_run: bool,
    cost_center_id: str | None = None,
    cost_center: str | None = None,
) -> OperationSummary:
    summary = OperationSummary()
    if dry_run:
        cost_center_display = cost_center_id or cost_center
        if not cost_center_display:
            raise ValueError("--cost-center or --cost-center-id is required for this operation")
        for username in usernames:
            print(f"[dry-run] Would add {username} to cost center {cost_center_display} in {enterprise}")
            summary.skipped += 1
        return summary

    resolved_cost_center_id = resolve_cost_center_id(client, enterprise, cost_center_id, cost_center)
    encoded_enterprise = quote(enterprise, safe="")
    encoded_cost_center_id = quote(resolved_cost_center_id, safe="")
    path = f"/enterprises/{encoded_enterprise}/settings/billing/cost-centers/{encoded_cost_center_id}/resource"
    try:
        client.post(path, {"users": usernames})
        summary.success = len(usernames)
        print(f"Added {len(usernames)} user(s) to cost center {resolved_cost_center_id}")
    except GitHubApiError as error:
        for username in usernames:
            summary.add_failure(username, error.status_code, error.message)
        print(f"Failed to add users to cost center {resolved_cost_center_id}: {error.message}", file=sys.stderr)
    return summary


def resolve_cost_center_id(
    client: GitHubClient,
    enterprise: str,
    cost_center_id: str | None = None,
    cost_center: str | None = None,
) -> str:
    identifier = cost_center_id or cost_center
    if not identifier:
        raise ValueError("--cost-center or --cost-center-id is required for this operation")
    if cost_center_id and not cost_center:
        return cost_center_id

    encoded_enterprise = quote(enterprise, safe="")
    response = client.get(f"/enterprises/{encoded_enterprise}/settings/billing/cost-centers")
    cost_centers = response.data.get("costCenters", []) if isinstance(response.data, dict) else []

    matches = [center for center in cost_centers if center.get("id") == identifier or center.get("name") == identifier]
    if len(matches) == 1:
        resolved_id = matches[0].get("id")
        if isinstance(resolved_id, str) and resolved_id:
            return resolved_id
    if len(matches) > 1:
        raise ValueError(f"Cost center identifier is ambiguous: {identifier}")

    available = ", ".join(sorted(center.get("name", "") for center in cost_centers if center.get("name")))
    raise ValueError(f"Cost center not found: {identifier}. Available cost centers: {available}")


def write_failures(path: str | Path, failures: list[Failure]) -> None:
    report_path = Path(path)
    if not failures:
        if report_path.exists():
            report_path.unlink()
        return
    with report_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=["username", "status_code", "message"])
        writer.writeheader()
        for failure in failures:
            writer.writerow(
                {
                    "username": failure.username,
                    "status_code": failure.status_code or "",
                    "message": failure.message,
                }
            )


def print_summary(summary: OperationSummary) -> None:
    print("\nSummary")
    print(f"  Success: {summary.success}")
    print(f"  Failed:  {summary.failed}")
    print(f"  Skipped: {summary.skipped}")
    if summary.failures:
        print("  Failed users written to failed_users.csv")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage GitHub organization, enterprise team, and cost center users.")
    add_common_arguments(parser)

    subparsers = parser.add_subparsers(dest="command", required=True)

    remove_parser = subparsers.add_parser("remove-from-org", help="Remove users from an organization.")
    add_common_arguments(remove_parser, suppress_defaults=True)
    remove_parser.add_argument("--org", help="Organization name.")

    remove_non_owners_parser = subparsers.add_parser(
        "remove-non-owners-from-org",
        help="Remove all non-owner members from an organization.",
    )
    add_common_arguments(remove_non_owners_parser, suppress_defaults=True)
    remove_non_owners_parser.add_argument("--org", help="Organization name.")

    team_parser = subparsers.add_parser("add-to-team", help="Add users to an enterprise team.")
    add_common_arguments(team_parser, suppress_defaults=True)
    team_parser.add_argument("--team", help="Enterprise team slug or ID.")

    cost_center_parser = subparsers.add_parser("add-to-cost-center", help="Add users to a billing cost center.")
    add_common_arguments(cost_center_parser, suppress_defaults=True)
    cost_center_parser.add_argument("--cost-center", help="Cost center name or ID.")
    cost_center_parser.add_argument("--cost-center-id", help="Cost center ID.")

    return parser


def add_common_arguments(parser: argparse.ArgumentParser, suppress_defaults: bool = False) -> None:
    default = argparse.SUPPRESS if suppress_defaults else None
    parser.add_argument("--config", default=default, dest="config_path", help="Path to a JSON configuration file.")
    parser.add_argument(
        "--token",
        default=argparse.SUPPRESS if suppress_defaults else os.environ.get("GITHUB_TOKEN"),
        help="GitHub PAT classic token. Defaults to GITHUB_TOKEN.",
    )
    parser.add_argument("--csv", default=default, dest="csv_path", help="Path to a CSV file with a username column.")
    parser.add_argument("--enterprise", default=default, help="Enterprise slug, for enterprise team and cost center operations.")
    parser.add_argument(
        "--base-url",
        default=default,
        help="GitHub API base URL. Use https://api.SUBDOMAIN.ghe.com for GHE.com.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=argparse.SUPPRESS if suppress_defaults else False,
        help="Print actions without calling the GitHub API.",
    )
    parser.add_argument(
        "--failed-csv",
        default=default,
        help="Where to write failed operations.",
    )


def load_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    with path.open(encoding="utf-8") as config_file:
        try:
            config = json.load(config_file)
        except json.JSONDecodeError as error:
            raise ValueError(f"Invalid JSON configuration file: {error}") from error
    if not isinstance(config, dict):
        raise ValueError("Configuration file must contain a JSON object")
    return config


def apply_config(args: argparse.Namespace) -> argparse.Namespace:
    config_path = getattr(args, "config_path", None)
    config: dict[str, Any] = load_config(config_path) if config_path else {}

    set_if_missing(args, "token", config.get("token"))
    set_if_missing(args, "csv_path", config.get("csv_path", config.get("csv")))
    set_if_missing(args, "enterprise", config.get("enterprise"))
    set_if_missing(args, "base_url", config.get("base_url"))
    set_if_missing(args, "failed_csv", config.get("failed_csv"))
    if not getattr(args, "dry_run", False) and config.get("dry_run") is True:
        args.dry_run = True

    command_config = config.get(args.command.replace("-", "_"), {}) if getattr(args, "command", None) else {}
    if command_config is not None and not isinstance(command_config, dict):
        raise ValueError(f"Configuration section for {args.command} must be a JSON object")
    if isinstance(command_config, dict):
        set_if_missing(args, "org", command_config.get("org"))
        set_if_missing(args, "team", command_config.get("team"))
        set_if_missing(args, "cost_center", command_config.get("cost_center", command_config.get("cost_center_name")))
        set_if_missing(args, "cost_center_id", command_config.get("cost_center_id"))

    set_if_missing(args, "base_url", DEFAULT_BASE_URL)
    set_if_missing(args, "failed_csv", "failed_users.csv")
    if not hasattr(args, "dry_run"):
        args.dry_run = False
    return args


def set_if_missing(args: argparse.Namespace, attr: str, value: Any) -> None:
    if value is None:
        return
    if not hasattr(args, attr) or getattr(args, attr) in {None, ""}:
        setattr(args, attr, value)


def run(args: argparse.Namespace) -> OperationSummary:
    args = apply_config(args)
    csv_commands = {"remove-from-org", "add-to-team", "add-to-cost-center"}
    if args.command in csv_commands and not getattr(args, "csv_path", None):
        raise ValueError("--csv is required")
    if not args.dry_run and not args.token:
        raise ValueError("GitHub token is required. Pass --token or set GITHUB_TOKEN.")

    client = GitHubClient(args.token or "dry-run-token", base_url=args.base_url)

    if args.command == "remove-from-org":
        usernames = read_usernames(args.csv_path)
        if not usernames:
            raise ValueError("CSV file did not contain any usernames")
        require_value(args.org, "--org")
        return remove_from_org(client=client, org=args.org, usernames=usernames, dry_run=args.dry_run)
    if args.command == "remove-non-owners-from-org":
        require_value(args.org, "--org")
        return remove_non_owners_from_org(client=client, org=args.org, dry_run=args.dry_run)
    if args.command == "add-to-team":
        usernames = read_usernames(args.csv_path)
        if not usernames:
            raise ValueError("CSV file did not contain any usernames")
        require_enterprise(args.enterprise)
        require_value(args.team, "--team")
        return add_to_enterprise_team(
            client=client,
            enterprise=args.enterprise,
            team=args.team,
            usernames=usernames,
            dry_run=args.dry_run,
        )
    if args.command == "add-to-cost-center":
        usernames = read_usernames(args.csv_path)
        if not usernames:
            raise ValueError("CSV file did not contain any usernames")
        require_enterprise(args.enterprise)
        return add_to_cost_center(
            client=client,
            enterprise=args.enterprise,
            cost_center_id=args.cost_center_id,
            cost_center=getattr(args, "cost_center", None),
            usernames=usernames,
            dry_run=args.dry_run,
        )
    raise ValueError(f"Unsupported command: {args.command}")


def require_enterprise(enterprise: str | None) -> None:
    if not enterprise:
        raise ValueError("--enterprise is required for this operation")


def require_value(value: str | None, option_name: str) -> None:
    if not value:
        raise ValueError(f"{option_name} is required for this operation")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args = apply_config(args)
        summary = run(args)
        write_failures(args.failed_csv, summary.failures)
        print_summary(summary)
        return 1 if summary.failed else 0
    except (FileNotFoundError, ValueError, GitHubApiError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())