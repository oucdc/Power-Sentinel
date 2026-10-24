# Security Policy

## Supported versions

Security fixes are provided for the latest 1.0.x release. Older releases may not receive updates.

## Reporting a vulnerability

Please do **not** open a public issue for a security problem.

Use GitHub's private vulnerability reporting for this repository:

1. Open the repository's **Security** tab.
2. Select **Report a vulnerability**.
3. Include the affected version, reproduction steps and impact.

If private reporting is unavailable, contact the maintainers through the repository before disclosing
details publicly.

## Scope

This application:

- runs with the current user's privileges and does not request elevation;
- performs no network requests and contains no telemetry;
- reads hardware counters, WMI/ACPI battery data and process CPU times;
- writes configuration, logs and an optional fallback data directory;
- copies diagnostics to the clipboard only after an explicit user action.

Useful reports include unsafe path handling, privilege escalation, log/config data exposure, and
unexpected network activity. Hardware accuracy differences without a security impact belong in a
normal bug report.

## Disclosure

Please allow reasonable time for a fix before public disclosure. Contributors will be credited unless
they ask to remain anonymous.
