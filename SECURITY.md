# Security Policy

## Supported Versions

Only the current production deployment (tracked on the `main` branch) receives security fixes. No prior versions are maintained.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report vulnerabilities privately using [GitHub's private security advisory feature](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability) on this repository. You can also reach the maintainer directly at **gx1400@gmail.com**.

Include as much of the following as possible:

- Type of vulnerability (e.g. XSS, SQL injection, authentication bypass, data exposure)
- File path(s) and line numbers where the issue is located
- Steps to reproduce
- Proof-of-concept or exploit code (if available)
- Potential impact — what data or functionality is affected

## What to Expect

This is a personal project maintained by a single developer. Response times are best-effort:

- **Acknowledgement:** within a few days
- **Assessment:** within one week
- **Fix (if confirmed):** timeline depends on severity; critical issues affecting user data are prioritised

I will credit reporters in the fix commit or release notes unless you prefer to remain anonymous.

## Scope

**In scope:**
- Authentication and authorisation flaws
- Data exposure — WIF files, uploaded photos, personal weaving data belonging to other users
- Injection vulnerabilities (SQL, command, template)
- Storage access control issues (S3 bucket policies, signed URL abuse)
- Unsafe direct object references

**Out of scope:**
- Denial-of-service attacks
- Rate limiting bypass that does not result in data exposure
- Vulnerabilities in third-party dependencies not yet addressed by the upstream maintainer
- Issues requiring physical access to the server

## Disclosure

Once a fix is deployed, I aim to publish a brief advisory describing the vulnerability, its impact, and the fix. Coordinated disclosure (embargo until fix ships) is preferred.

## Note on AI-Assisted Development

This application was built with significant AI (Claude) assistance. Automated tests, a CI pipeline, and code review are in place. If you find a class of vulnerability that suggests a systematic gap in the review process, please mention it — that context is as valuable as the specific finding.
