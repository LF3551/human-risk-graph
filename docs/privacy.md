# Privacy, GDPR and works councils

Human Risk Graph analyses who approves, releases and can bypass controls. Those are facts
about identifiable people, so in the EU running it is processing personal data, and in
Germany a tool like this is typically subject to co-determination by the works council. This
page describes what HRG processes and the features that support a compliant deployment. It
is engineering documentation, not legal advice: involve your data protection officer (DPO)
and, where one exists, the works council before the first run on real data.

## What HRG processes

| Data | Where it comes from | Used for |
|---|---|---|
| Person id (for example a GitHub login), name, role | The organization file; `hrg scan github` takes logins from the GitHub API | Identifying nodes in the graph and in reports |
| Criticality (0-1) | Set by whoever maintains the file; the scan drafts a value | Weighting the risk |
| Dependencies: who approves, escalates to or can bypass whom | The file; the scan derives them from pull request reviews, CODEOWNERS and branch rules | All metrics |
| Functions: who can merge, release, administer, deploy | The file; the scan derives them from the same sources and from deployment environments | Model hrg-3 |
| Last activity (one date, or `never`) of people with authority over a function | The file; the scan takes the latest date from the pull requests, releases and deployments it reads, or the person's last commit. `--no-activity` turns it off | Model hrg-3: the inactive-performer finding (HRG007), a periodic review of access rights |
| Free-text evidence | Written by the scan or by hand | Review of the draft |

HRG does **not** read message contents, code, working hours or performance data, and it
keeps no activity timelines: at most one date per person with authority, the last time
they were seen active, so that authority nobody uses any more can be found and removed.
It does not send any data anywhere: it runs locally or in your CI, has
no telemetry and makes no network calls except the GitHub API calls of `hrg scan github`,
with your token.

## What HRG is for, and what it is not

HRG measures **organizational** risk: whether a control depends on one person, whether
authority is concentrated, whether a two-person rule can be bypassed. Its findings are about
the structure ("only one person can publish a release"), not about how well anyone works.
It must not be used to assess the performance or conduct of employees. Writing that purpose
down, and the exclusion of performance assessment, is the core of an agreement with a works
council (in Germany, Section 87(1) no. 6 BetrVG covers technical systems *suitable* for
monitoring employees, whatever the intent).

## Pseudonymization

`--pseudonymize` (or `pseudonymize = true` in `hrg.toml`) replaces every person by a keyed
pseudonym in all reports, the graph and `hrg diff`:

```bash
export HRG_PSEUDONYM_KEY="$(cat /run/secrets/hrg-key)"   # at least 16 characters
hrg analyze org.yaml --pseudonymize
```

- **Keyed pseudonyms.** A pseudonym is `P-` and the first 8 hex digits of
  HMAC-SHA256(key, id). GitHub logins and e-mail addresses are easy to guess, so an unkeyed
  hash could be reversed by trying candidates; with a secret key it cannot. The same key
  gives the same pseudonyms on every run, so snapshots stay comparable and `hrg diff` works.
- **Allow-listed fields.** Only id, criticality, last activity, source and confirmation of people; from,
  to, type, weight and review of dependencies; and id, name, criticality, requires,
  separation, performers, alone, source and confirmation of functions reach the analysis.
  Names, roles, e-mail addresses, evidence and any other field are dropped.
- **Free text.** Known ids and names are replaced in the text that is kept: coverage gaps,
  the input file name and the reasons of risk acceptances. Risk acceptances keep matching
  their findings.
- **Without a key** HRG uses a random key, warns, and the pseudonyms change on every run.
  That is enough for a one-off anonymous report but not for comparisons.
- **SARIF** results still point at the right line of the organization file (the file keeps
  its own ids); the messages use pseudonyms.

Pseudonymized data is still personal data under the GDPR (Art. 4(5)) for whoever holds the
key and the original file; it is a safeguard (Art. 25, Art. 32), not anonymization. It lets
a security team, auditors or a dashboard work with the structure while only the key holder
can say who is who.

### Re-identification

Whoever holds the key and the original file can resolve pseudonyms, for example to act on a
finding with the person concerned:

```bash
HRG_PSEUDONYM_KEY=... hrg pseudonyms org.yaml > pseudonyms.csv   # pseudonym,id,name
```

A typical arrangement: the key is stored in a secret store readable by the DPO (or a role
agreed with the works council), reports are shared pseudonymized, and re-identification is
requested and logged through a ticket.

### In GitHub Actions

```yaml
- uses: LF3551/human-risk-graph@v0.16.0
  env:
    HRG_PSEUDONYM_KEY: ${{ secrets.HRG_PSEUDONYM_KEY }}
  with:
    scan-org: my-org
    pseudonymize: true
```

With `pseudonymize: true` the draft written by the scan, which has real logins, stays in the
runner's temporary directory and is not uploaded with the report artifact. The job summary,
the artifact and the SARIF messages are pseudonymized.

## Checklist for a deployment

1. **Purpose and legal basis.** Write down the purpose (organizational resilience and
   segregation of duties, for example for ISO/IEC 27001 A.5.3 and A.5.29 or DORA Art. 9 and
   11) and the legal basis with your DPO, typically legitimate interest (GDPR Art. 6(1)(f)),
   or for employees a works agreement under Art. 88 GDPR. In Germany, check with your DPO
   how far Section 26 BDSG still applies after the CJEU judgment C-34/21 (2023).
2. **Works council.** Agree the purpose, the data, who sees named results, the exclusion of
   performance assessment, retention, and the re-identification process; a works agreement
   (Betriebsvereinbarung) is the usual form in Germany.
3. **DPIA.** Assess whether a data protection impact assessment (GDPR Art. 35) is required.
   This page and the table above are a starting point for its description of the processing.
4. **Record of processing.** Add the processing to the record of processing activities
   (Art. 30).
5. **Minimize.** Use `--pseudonymize` for anything shared beyond the people who must act on
   findings; scan only the repositories in scope (`--max-repos`, or one repository at a
   time); delete drafts and reports you no longer need. If the inactive-performer finding
   is not part of the agreed purpose, scan with `--no-activity` so that no activity date
   is recorded.
6. **Inform.** Tell the people concerned what is analysed and why (Art. 13/14), for example
   in the engineering handbook.
7. **Access.** Keep the pseudonym key, the drafts with real names and the named reports
   where only the agreed roles can read them.

## Retention

HRG keeps nothing between runs. Drafts (`*-org.yaml`), reports and the GitHub Actions
artifact are files you control; set an artifact retention period
(`retention-days` in `actions/upload-artifact`, or the repository default) that matches what
you agreed.
