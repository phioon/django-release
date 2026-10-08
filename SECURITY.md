# Security reporting

Please do not put secrets, database connection strings, private service identities,
or raw provider logs in a public issue or pull request.

Use GitHub private vulnerability reporting if it is enabled for this repository:
open the repository's Security tab and choose **Report a vulnerability**. Otherwise,
check the repository's Security advisories for an available private reporting
route. No private email address or guaranteed private reporting channel is
currently designated by this project. If no private route is available, do not
post exploit details or sensitive evidence publicly; you may open a minimal public
request asking maintainers to enable a private channel, without disclosing the
vulnerability.

Report the affected full action commit SHA, impact, and a minimal fictional
reproduction through the private route when available. Retain uncertain release
records while containing affected workflows. Never paste live tokens. Rotate an
exposed credential through its owner's established process.

Consumers pin commits; fixes require reviewed pin-update pull requests. There is
no promise that moving a tag updates existing consumers, no support-window
commitment for old pins, and no hosted security qualification implied by offline
tests. See [security and recovery](docs/security-recovery.md) for the trust boundary,
upgrade compatibility, and forward-recovery rules.
