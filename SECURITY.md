# Security Policy

## Supported Versions

Security fixes are made in the latest version of MLogger on the `main` branch. Please reproduce the problem on the current version before reporting it.

## Reporting a Vulnerability

Report privately — **do not open a public issue or pull request for a suspected vulnerability.**

Use GitHub's private reporting form: open the **Security** tab of the repository and choose **Report a vulnerability**. Please include:

- what an attacker can do and under which conditions
- the steps to reproduce it
- the version or commit you tested

You will get a reply as soon as the report has been looked at, and you will be credited in the changelog unless you prefer otherwise.

## Security Model

Knowing what MLogger does and does not protect against helps to tell a vulnerability from expected behavior:

- By default the server listens on `127.0.0.1` only. It rejects requests that arrive under an unknown host name and write requests that come from another website.
- There is **no authentication**. With `--host 0.0.0.0` anyone on the network can read and change the data. This mode is meant for trusted networks only.
- The import feature reads log folders from the disk of the machine the server runs on, on behalf of whoever can reach the server.
- All data stays on your machine: MLogger makes no outgoing connections.
